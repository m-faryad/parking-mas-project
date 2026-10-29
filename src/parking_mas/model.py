"""Agents of the parking multi-agent system.

* :class:`ParkingSpaceAgent` - resource agent owning its occupancy state; refuses
  illegal transitions.
* :class:`CarParkAgent`      - owns spaces, answers availability queries, executes
  allocations/releases.
* :class:`VehicleAgent`      - requests parking, evaluates offers against its own
  walking limit, keeps a life-cycle state and history.
* :class:`ManagementAgent`   - coordinator: receives requests, queries car parks,
  ranks candidates with the selected strategy, negotiates offers with the vehicle
  and enforces global invariants.

Communication is an explicit :class:`Message` structure routed through a
:class:`MessageBus` (request -> availability query/reply -> offer -> accept/decline).
It is centralised request/offer negotiation with one manager.  It is NOT a
decentralised or market-based protocol.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .config import ELIGIBILITY, SPACE_TYPES, CarParkConfig

if TYPE_CHECKING:  # pragma: no cover
    from .strategies import Strategy


class AllocationError(RuntimeError):
    """An allocation/release that would violate an invariant."""


class UnknownVehicleError(AllocationError):
    """Vehicle is not currently holding an allocation."""


# --------------------------------------------------------------------------- #
# messaging
# --------------------------------------------------------------------------- #
@dataclass
class Message:
    time: float
    sender: str
    receiver: str
    kind: str  # request | availability_query | availability_reply | offer | accept | decline | release
    payload: dict[str, Any] = field(default_factory=dict)


class MessageBus:
    """Records message counts for every message and keeps the most recent ones."""

    def __init__(self, keep: int = 2000) -> None:
        self.keep = keep
        self.counts: dict[str, int] = {}
        self.recent: list[Message] = []

    def send(self, msg: Message) -> None:
        self.counts[msg.kind] = self.counts.get(msg.kind, 0) + 1
        if self.keep:
            self.recent.append(msg)
            if len(self.recent) > self.keep:
                del self.recent[: len(self.recent) - self.keep]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


# --------------------------------------------------------------------------- #
# parking space agent
# --------------------------------------------------------------------------- #
class ParkingSpaceAgent:
    __slots__ = ("space_id", "car_park", "space_type", "index", "drive_m", "walk_m",
                 "occupant", "history", "n_allocations")

    def __init__(self, space_id: str, car_park: str, space_type: str, index: int,
                 drive_m: float, walk_m: float) -> None:
        if space_type not in SPACE_TYPES:
            raise AllocationError(f"unknown space type {space_type!r}")
        self.space_id = space_id
        self.car_park = car_park
        self.space_type = space_type
        self.index = index
        self.drive_m = drive_m  # drive distance from campus entrance to this space
        self.walk_m = walk_m  # walk distance from this space to the destination
        self.occupant: str | None = None
        self.history: list[tuple[float, str, str]] = []  # (time, 'occupy'|'release', vehicle_id)
        self.n_allocations = 0

    @property
    def available(self) -> bool:
        return self.occupant is None

    def eligible_for(self, vehicle_type: str) -> bool:
        return self.space_type in ELIGIBILITY[vehicle_type]

    def occupy(self, vehicle_id: str, t: float) -> None:
        if self.occupant is not None:
            raise AllocationError(f"{self.space_id} already occupied by {self.occupant}")
        self.occupant = vehicle_id
        self.n_allocations += 1
        self.history.append((t, "occupy", vehicle_id))

    def release(self, vehicle_id: str, t: float) -> None:
        if self.occupant is None:
            raise AllocationError(f"{self.space_id} is already free")
        if self.occupant != vehicle_id:
            raise AllocationError(f"{self.space_id} is held by {self.occupant}, not {vehicle_id}")
        self.occupant = None
        self.history.append((t, "release", vehicle_id))


# --------------------------------------------------------------------------- #
# car park agent
# --------------------------------------------------------------------------- #
@dataclass
class Candidate:
    """A free space proposed by a car park agent in an availability reply."""

    space: ParkingSpaceAgent
    car_park_occupancy: float  # occupancy ratio of the car park at query time

    @property
    def drive_m(self) -> float:
        return self.space.drive_m

    @property
    def walk_m(self) -> float:
        return self.space.walk_m


class CarParkAgent:
    def __init__(self, cfg: CarParkConfig, order: int) -> None:
        self.cfg = cfg
        self.name = cfg.name
        self.order = order  # fixed position used by the baseline strategy
        self.spaces: list[ParkingSpaceAgent] = []
        self._free: dict[str, list[int]] = {t: [] for t in SPACE_TYPES}
        self.occupied = 0
        counts = {"accessible": cfg.accessible, "standard": cfg.standard, "ev": cfg.ev}
        idx = 0
        for stype in SPACE_TYPES:  # accessible nearest, standard, EV bays at the rear
            for _ in range(counts[stype]):
                sp = ParkingSpaceAgent(
                    f"{cfg.name[:3].upper()}{order}-{idx:03d}", cfg.name, stype, idx,
                    drive_m=cfg.gate_distance_m + idx * cfg.pitch_m,
                    walk_m=cfg.walk_base_m + idx * cfg.pitch_m,
                )
                self.spaces.append(sp)
                self._free[stype].append(idx)
                idx += 1
        self.by_id = {s.space_id: s for s in self.spaces}

    @property
    def capacity(self) -> int:
        return len(self.spaces)

    @property
    def occupancy_ratio(self) -> float:
        return self.occupied / self.capacity if self.capacity else 0.0

    def free_count(self, space_type: str | None = None) -> int:
        if space_type is None:
            return self.capacity - self.occupied
        return len(self._free[space_type])

    def query(self, vehicle_type: str) -> list[Candidate]:
        """Availability reply: the lowest-index free space of each eligible type.

        Within a type, drive and walk distance both grow with the space index, so
        the first free space of a type dominates every later one for any strategy
        whose cost is monotone in distance (tested against brute force).
        """
        occ = self.occupancy_ratio
        out = []
        for stype in ELIGIBILITY[vehicle_type]:
            if self._free[stype]:
                out.append(Candidate(self.spaces[self._free[stype][0]], occ))
        return out

    def all_free_spaces(self, vehicle_type: str) -> list[ParkingSpaceAgent]:
        return [self.spaces[i] for st in ELIGIBILITY[vehicle_type] for i in self._free[st]]

    def allocate(self, space: ParkingSpaceAgent, vehicle_id: str, vehicle_type: str, t: float) -> None:
        if space.car_park != self.name or self.by_id.get(space.space_id) is not space:
            raise AllocationError(f"{space.space_id} does not belong to {self.name}")
        if not space.eligible_for(vehicle_type):
            raise AllocationError(f"{space.space_id} ({space.space_type}) not eligible for {vehicle_type}")
        if self.occupied >= self.capacity:
            raise AllocationError(f"{self.name} is at capacity")
        space.occupy(vehicle_id, t)  # raises if already occupied (state unchanged)
        self._free[space.space_type].remove(space.index)
        self.occupied += 1

    def release(self, space: ParkingSpaceAgent, vehicle_id: str, t: float) -> None:
        space.release(vehicle_id, t)
        bisect.insort(self._free[space.space_type], space.index)
        self.occupied -= 1

    def check_invariants(self) -> None:
        occ = sum(1 for s in self.spaces if s.occupant is not None)
        if occ != self.occupied or occ > self.capacity:
            raise AllocationError(f"{self.name}: occupancy counter {self.occupied} != actual {occ}")
        for st in SPACE_TYPES:
            free_actual = [s.index for s in self.spaces if s.space_type == st and s.occupant is None]
            if free_actual != self._free[st]:
                raise AllocationError(f"{self.name}: free list for {st} out of sync")


# --------------------------------------------------------------------------- #
# vehicle agent
# --------------------------------------------------------------------------- #
class VehicleAgent:
    NEW, WAITING, PARKED, DEPARTED, FAILED, INVALID = "new", "waiting", "parked", "departed", "failed", "invalid"

    def __init__(self, vehicle_id: str, vehicle_type: str, arrival_min: float, duration_min: float,
                 patience_min: float, max_walk_m: float) -> None:
        self.vehicle_id = vehicle_id
        self.vehicle_type = vehicle_type
        self.arrival_min = arrival_min
        self.duration_min = duration_min
        self.patience_min = patience_min
        self.max_walk_m = max_walk_m
        self.state = self.NEW
        self.request_time: float | None = None
        self.alloc_time: float | None = None
        self.depart_time: float | None = None
        self.space: ParkingSpaceAgent | None = None
        self.offers_declined = 0
        self.fail_reason = ""
        self.history: list[tuple[float, str]] = []

    def note(self, t: float, what: str) -> None:
        self.history.append((t, what))

    def is_valid(self) -> bool:
        return (self.vehicle_type in ELIGIBILITY and self.duration_min > 0
                and self.arrival_min >= 0 and self.patience_min >= 0 and self.max_walk_m > 0)

    def evaluate_offer(self, cand: Candidate) -> bool:
        """Vehicle-side decision: accept unless the walk exceeds the driver's limit."""
        return cand.walk_m <= self.max_walk_m and cand.space.eligible_for(self.vehicle_type)


# --------------------------------------------------------------------------- #
# management agent
# --------------------------------------------------------------------------- #
@dataclass
class Decision:
    success: bool
    vehicle_id: str
    strategy: str
    time: float
    n_considered: int
    considered: list[str]
    chosen: ParkingSpaceAgent | None
    score: float | None
    declined: int
    reason: str
    compute_us: float = 0.0


class ManagementAgent:
    def __init__(self, car_parks: list[CarParkAgent], strategy: Strategy, bus: MessageBus | None = None) -> None:
        self.car_parks = car_parks
        self.strategy = strategy
        self.bus = bus or MessageBus()
        self.active: dict[str, ParkingSpaceAgent] = {}  # vehicle_id -> space
        self._cp = {c.name: c for c in car_parks}

    @property
    def capacity(self) -> int:
        return sum(c.capacity for c in self.car_parks)

    @property
    def occupied(self) -> int:
        return sum(c.occupied for c in self.car_parks)

    def request_parking(self, v: VehicleAgent, t: float) -> Decision:
        """Handle one request.  Never changes occupancy unless an offer is accepted."""
        import time as _time
        t0 = _time.perf_counter()
        bus = self.bus
        bus.send(Message(t, v.vehicle_id, "manager", "request", {"type": v.vehicle_type}))
        if v.vehicle_id in self.active:
            raise AllocationError(f"{v.vehicle_id} already holds an allocation")
        candidates: list[Candidate] = []
        for cp in self.car_parks:
            bus.send(Message(t, "manager", cp.name, "availability_query", {"type": v.vehicle_type}))
            reply = cp.query(v.vehicle_type)
            bus.send(Message(t, cp.name, "manager", "availability_reply", {"n": len(reply)}))
            candidates.extend(reply)
        ranked = self.strategy.rank(v, candidates)
        considered = [c.space.space_id for c, _ in ranked]
        declined = 0
        for cand, score in ranked:
            bus.send(Message(t, "manager", v.vehicle_id, "offer", {"space": cand.space.space_id}))
            if v.evaluate_offer(cand):
                bus.send(Message(t, v.vehicle_id, "manager", "accept", {"space": cand.space.space_id}))
                self._cp[cand.space.car_park].allocate(cand.space, v.vehicle_id, v.vehicle_type, t)
                self.active[v.vehicle_id] = cand.space
                return Decision(True, v.vehicle_id, self.strategy.name, t, len(ranked), considered,
                                cand.space, score, declined,
                                f"selected {cand.space.space_id} ({cand.space.space_type}) in {cand.space.car_park}: "
                                f"{self.strategy.explain(v, cand, score)}",
                                (_time.perf_counter() - t0) * 1e6)
            declined += 1
            bus.send(Message(t, v.vehicle_id, "manager", "decline",
                             {"space": cand.space.space_id, "walk_m": cand.walk_m, "limit_m": v.max_walk_m}))
        reason = "no eligible space free" if not ranked else "all offers declined (walk limit exceeded)"
        return Decision(False, v.vehicle_id, self.strategy.name, t, len(ranked), considered, None, None,
                        declined, reason, (_time.perf_counter() - t0) * 1e6)

    def release(self, vehicle_id: str, t: float) -> ParkingSpaceAgent:
        space = self.active.get(vehicle_id)
        if space is None:
            raise UnknownVehicleError(f"{vehicle_id} holds no allocation (unknown or already departed)")
        self.bus.send(Message(t, vehicle_id, "manager", "release", {"space": space.space_id}))
        self._cp[space.car_park].release(space, vehicle_id, t)
        del self.active[vehicle_id]
        return space

    def check_invariants(self) -> None:
        for cp in self.car_parks:
            cp.check_invariants()
        if self.occupied != len(self.active):
            raise AllocationError("active allocations do not match occupied spaces")
        holders = [s.occupant for cp in self.car_parks for s in cp.spaces if s.occupant]
        if len(holders) != len(set(holders)):
            raise AllocationError("a vehicle holds more than one space")
        if self.occupied > self.capacity:
            raise AllocationError("occupancy exceeds capacity")

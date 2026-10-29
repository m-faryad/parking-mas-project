"""Discrete-event simulation engine.

Simulated time is measured in minutes from the start of the observation window
(minute 0).  It is advanced by jumping between events held in a priority queue,
so it has no relationship with wall-clock time.  Wall-clock time is only used to
measure the manager's decision computation time (``compute_us``), which is a
non-deterministic, separate quantity.

Event priority at the same simulated minute: departures, abandonments,
arrivals, occupancy samples.
"""

from __future__ import annotations

import heapq
import math
from typing import Any

import pandas as pd

from .config import ScenarioConfig
from .datagen import generate_arrivals
from .model import CarParkAgent, ManagementAgent, MessageBus, VehicleAgent
from .strategies import make_strategy

DEPART, ABANDON, ARRIVE, SAMPLE = 0, 1, 2, 3


class Simulation:
    def __init__(self, cfg: ScenarioConfig, strategy: str = "coordinated",
                 arrivals: pd.DataFrame | None = None, keep_messages: int = 2000) -> None:
        cfg.validate()
        self.cfg = cfg
        self.strategy_name = strategy
        self.arrivals = generate_arrivals(cfg) if arrivals is None else arrivals
        self.car_parks = [CarParkAgent(c, i) for i, c in enumerate(cfg.car_parks)]
        self.bus = MessageBus(keep=keep_messages)
        self.manager = ManagementAgent(self.car_parks, make_strategy(strategy, cfg), self.bus)
        self.horizon = float(cfg.duration_min)
        self.now = 0.0
        self.finished = False
        self.vehicles: dict[str, VehicleAgent] = {}
        self.queue: list[VehicleAgent] = []
        self.decisions: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.samples: list[dict[str, Any]] = []
        self._heap: list[tuple[float, int, int, str]] = []
        self._seq = 0
        self._last_t = 0.0
        self._area_total = 0.0
        self._area_cp = {cp.name: 0.0 for cp in self.car_parks}
        self._last_reason: dict[str, str] = {}
        self._schedule_all()

    # ------------------------------------------------------------------ setup
    def _push(self, t: float, prio: int, vid: str) -> None:
        self._seq += 1
        heapq.heappush(self._heap, (t, prio, self._seq, vid))

    def _schedule_all(self) -> None:
        seen: set[str] = set()
        for row in self.arrivals.itertuples(index=False):
            vid = str(row.vehicle_id)
            if vid in seen:  # duplicate ids would break the one-allocation invariant bookkeeping
                vid = f"{vid}#dup{len(seen)}"
            seen.add(vid)
            vals = (row.arrival_min, row.duration_min, row.patience_min, row.max_walk_m)
            if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals) or not isinstance(
                    row.vehicle_type, str):
                a, d, p, w = (-1.0 if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
                              for v in vals)
                veh = VehicleAgent(vid, str(row.vehicle_type), max(a, 0.0), -1.0, p, w)
            else:
                veh = VehicleAgent(vid, row.vehicle_type, float(row.arrival_min), float(row.duration_min),
                                   float(row.patience_min), float(row.max_walk_m))
            if veh.arrival_min > self.horizon:
                continue  # outside the observation window
            self.vehicles[vid] = veh
            self._push(veh.arrival_min, ARRIVE, vid)
        t = 0.0
        while t <= self.horizon + 1e-9:
            self._push(t, SAMPLE, "")
            t += self.cfg.sample_interval_min

    # --------------------------------------------------------------- core loop
    def _advance(self, t: float) -> None:
        dt = t - self._last_t
        if dt > 0:
            self._area_total += self.manager.occupied * dt
            for cp in self.car_parks:
                self._area_cp[cp.name] += cp.occupied * dt
            self._last_t = t
        self.now = t

    def step(self, until: float) -> int:
        """Process every event with time <= ``until`` (capped at the horizon)."""
        until = min(until, self.horizon)
        n = 0
        while self._heap and self._heap[0][0] <= until:
            t, prio, _, vid = heapq.heappop(self._heap)
            self._advance(t)
            if prio == DEPART:
                self._on_depart(self.vehicles[vid], t)
            elif prio == ABANDON:
                self._on_abandon(self.vehicles[vid], t)
            elif prio == ARRIVE:
                self._on_arrive(self.vehicles[vid], t)
            else:
                self._on_sample(t)
            n += 1
        self._advance(until)
        if until >= self.horizon:
            self.finished = True
            self.manager.check_invariants()
        return n

    def run(self) -> Simulation:
        self.step(self.horizon)
        return self

    # ------------------------------------------------------------- event logic
    def _log_event(self, t: float, event: str, v: VehicleAgent, space: str = "", detail: str = "") -> None:
        self.events.append({"time": round(t, 3), "event": event, "vehicle_id": v.vehicle_id,
                            "vehicle_type": v.vehicle_type, "space_id": space, "detail": detail})

    def _log_decision(self, t: float, v: VehicleAgent, d, attempt: str) -> None:
        self.decisions.append({
            "time": round(t, 3), "vehicle_id": v.vehicle_id, "vehicle_type": v.vehicle_type,
            "strategy": d.strategy, "attempt": attempt, "n_candidates": d.n_considered,
            "candidates": ";".join(d.considered), "offers_declined": d.declined,
            "outcome": "allocated" if d.success else "not_allocated",
            "space_id": d.chosen.space_id if d.chosen else "",
            "car_park": d.chosen.car_park if d.chosen else "",
            "score": None if d.score is None else round(d.score, 2),
            "reason": d.reason, "compute_us": round(d.compute_us, 1),
        })

    def _try_allocate(self, v: VehicleAgent, t: float, attempt: str) -> bool:
        d = self.manager.request_parking(v, t)
        v.offers_declined += d.declined
        if d.success:
            v.state = VehicleAgent.PARKED
            v.alloc_time = t
            v.space = d.chosen
            v.note(t, f"parked in {d.chosen.space_id}")
            self._log_decision(t, v, d, attempt)
            self._log_event(t, "allocate", v, d.chosen.space_id, d.reason)
            self._push(t + v.duration_min, DEPART, v.vehicle_id)
            return True
        self._last_reason[v.vehicle_id] = d.reason
        if attempt == "first":
            self._log_decision(t, v, d, attempt)
        return False

    def _on_arrive(self, v: VehicleAgent, t: float) -> None:
        if not v.is_valid():
            v.state = VehicleAgent.INVALID
            v.fail_reason = "invalid_request"
            self._log_event(t, "reject_invalid", v, "", "invalid request fields")
            return
        v.request_time = t
        self._log_event(t, "request", v)
        if self._try_allocate(v, t, "first"):
            return
        if v.patience_min > 0:
            v.state = VehicleAgent.WAITING
            self.queue.append(v)
            self._push(t + v.patience_min, ABANDON, v.vehicle_id)
            self._log_event(t, "wait", v, "", self._last_reason[v.vehicle_id])
        else:
            v.state = VehicleAgent.FAILED
            v.fail_reason = "no_wait"
            v.depart_time = t
            self._log_event(t, "fail", v, "", f"no_wait: {self._last_reason[v.vehicle_id]}")

    def _on_depart(self, v: VehicleAgent, t: float) -> None:
        space = self.manager.release(v.vehicle_id, t)
        v.state = VehicleAgent.DEPARTED
        v.depart_time = t
        v.note(t, f"left {space.space_id}")
        self._log_event(t, "depart", v, space.space_id)
        for w in list(self.queue):  # a space was freed: retry waiting vehicles in FIFO order
            if self._try_allocate(w, t, "retry"):
                self.queue.remove(w)

    def _on_abandon(self, v: VehicleAgent, t: float) -> None:
        if v.state != VehicleAgent.WAITING:
            return  # already parked
        self.queue.remove(v)
        v.state = VehicleAgent.FAILED
        v.depart_time = t
        v.fail_reason = ("timeout_full" if self._last_reason.get(v.vehicle_id, "").startswith("no eligible")
                         else "timeout_declined")
        self._log_event(t, "fail", v, "", v.fail_reason)

    def _on_sample(self, t: float) -> None:
        row: dict[str, Any] = {"time": round(t, 3), "occupied": self.manager.occupied,
                               "capacity": self.manager.capacity,
                               "occupancy_ratio": self.manager.occupied / self.manager.capacity,
                               "queue_length": len(self.queue)}
        for cp in self.car_parks:
            row[f"occ_{cp.name}"] = cp.occupied
        self.samples.append(row)

    # ----------------------------------------------------------------- results
    def snapshot(self) -> dict[str, Any]:
        st = self.status_counts()
        return {"time": self.now, "occupied": self.manager.occupied, "capacity": self.manager.capacity,
                "queue": len(self.queue), "finished": self.finished, **st,
                "car_parks": [{"name": cp.name, "occupied": cp.occupied, "capacity": cp.capacity,
                               "free_standard": cp.free_count("standard"), "free_ev": cp.free_count("ev"),
                               "free_accessible": cp.free_count("accessible")} for cp in self.car_parks]}

    def status_counts(self) -> dict[str, int]:
        c = {"requests": 0, "parked_total": 0, "failed": 0, "waiting": 0, "invalid": 0}
        for v in self.vehicles.values():
            if v.state == VehicleAgent.NEW:
                continue
            if v.state == VehicleAgent.INVALID:
                c["invalid"] += 1
                continue
            c["requests"] += 1
            if v.state in (VehicleAgent.PARKED, VehicleAgent.DEPARTED):
                c["parked_total"] += 1
            elif v.state == VehicleAgent.FAILED:
                c["failed"] += 1
            else:
                c["waiting"] += 1
        return c

    def vehicle_table(self) -> pd.DataFrame:
        rows = []
        for v in self.vehicles.values():
            if v.state == VehicleAgent.NEW:
                continue
            if v.state == VehicleAgent.INVALID:
                status, waited = "invalid", 0.0
            elif v.state in (VehicleAgent.PARKED, VehicleAgent.DEPARTED):
                status, waited = "served", v.alloc_time - v.request_time
            elif v.state == VehicleAgent.FAILED:
                status, waited = "failed", v.depart_time - v.request_time
            else:
                status, waited = "pending", self.now - v.request_time
            rows.append({
                "vehicle_id": v.vehicle_id, "vehicle_type": v.vehicle_type, "request_time": v.request_time,
                "duration_min": v.duration_min, "patience_min": v.patience_min, "max_walk_m": v.max_walk_m,
                "status": status, "fail_reason": v.fail_reason, "car_park": v.space.car_park if v.space else "",
                "space_id": v.space.space_id if v.space else "",
                "space_type": v.space.space_type if v.space else "",
                "alloc_time": v.alloc_time, "waited_min": waited,
                "drive_m": v.space.drive_m if v.space else None,
                "walk_m": v.space.walk_m if v.space else None,
                "offers_declined": v.offers_declined,
            })
        return pd.DataFrame(rows)

    @property
    def occupancy_area(self) -> tuple[float, dict[str, float]]:
        return self._area_total, dict(self._area_cp)

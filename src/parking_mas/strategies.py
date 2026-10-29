"""Allocation strategies.

Both strategies receive the candidates returned by the car-park agents
(the lowest-index free space of each eligible type per car park) and return them
ranked best-first.  The manager offers them in that order until a vehicle accepts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .config import STRATEGIES, ConfigError, ScenarioConfig

if TYPE_CHECKING:  # pragma: no cover
    from .model import Candidate, VehicleAgent


class Strategy:
    name = "abstract"

    def rank(self, vehicle: VehicleAgent, candidates: list[Candidate]) -> list[tuple[Candidate, float]]:
        raise NotImplementedError

    def explain(self, vehicle: VehicleAgent, cand: Candidate, score: float) -> str:
        return f"score={score:.1f}"


class BaselineFirstAvailable(Strategy):
    """Strategy A - first eligible free space in a fixed order.

    Order: car parks in their configured sequence, then lowest space index.
    Ignores distance, congestion and reserved-bay preservation.  O(#car parks).
    """

    name = "baseline"

    def __init__(self, order: dict[str, int]) -> None:
        self.order = order

    def rank(self, vehicle, candidates):
        ranked = sorted(candidates, key=lambda c: (self.order[c.space.car_park], c.space.index))
        return [(c, float(i)) for i, c in enumerate(ranked)]

    def explain(self, vehicle, cand, score):
        return "first eligible free space in fixed car-park order"


class CoordinatedStrategy(Strategy):
    """Strategy B - minimise a weighted cost over all candidate spaces.

    cost = w_drive * drive_m
         + w_walk  * walk_m * (accessible_walk_multiplier if accessible vehicle else 1)
         + w_congestion * occupancy_ratio(car park)
         - ev_bonus        (EV vehicle in an EV bay)
         - accessible_bonus (accessible vehicle in an accessible bay)

    Lower is better; ties break on car-park order then space index (deterministic).
    """

    name = "coordinated"

    def __init__(self, cfg: ScenarioConfig, order: dict[str, int]) -> None:
        self.cfg = cfg
        self.order = order

    def cost(self, vehicle: VehicleAgent, cand: Candidate) -> float:
        c = self.cfg
        walk_w = c.w_walk * (c.accessible_walk_multiplier if vehicle.vehicle_type == "accessible" else 1.0)
        cost = c.w_drive * cand.drive_m + walk_w * cand.walk_m + c.w_congestion * cand.car_park_occupancy
        if vehicle.vehicle_type == "ev" and cand.space.space_type == "ev":
            cost -= c.ev_bonus
        if vehicle.vehicle_type == "accessible" and cand.space.space_type == "accessible":
            cost -= c.accessible_bonus
        return cost

    def rank(self, vehicle, candidates):
        scored = [(self.cost(vehicle, c), self.order[c.space.car_park], c.space.index, c) for c in candidates]
        scored.sort(key=lambda x: x[:3])
        return [(c, s) for s, _, _, c in scored]

    def explain(self, vehicle, cand, score):
        return (f"lowest weighted cost {score:.1f} (drive {cand.drive_m:.0f} m, walk {cand.walk_m:.0f} m, "
                f"car park {cand.car_park_occupancy:.0%} full)")


def make_strategy(name: str, cfg: ScenarioConfig) -> Strategy:
    order = {cp.name: i for i, cp in enumerate(cfg.car_parks)}
    if name == "baseline":
        return BaselineFirstAvailable(order)
    if name == "coordinated":
        return CoordinatedStrategy(cfg, order)
    raise ConfigError(f"unknown strategy {name!r}; choose one of {STRATEGIES}")

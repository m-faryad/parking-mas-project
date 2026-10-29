"""Scenario configuration, validation and the predefined scenarios.

All numbers in the predefined scenarios are *synthetic modelling choices*, not
measurements of any real car park.  The emission factors are illustrative,
configurable assumptions (see docs/metrics.md).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

VEHICLE_TYPES = ("standard", "ev", "accessible")
SPACE_TYPES = ("accessible", "standard", "ev")  # order = layout order along the aisle
STRATEGIES = ("baseline", "coordinated")

# vehicle type -> space types it may use (reserved bays are never given to
# vehicles without the matching requirement)
ELIGIBILITY: dict[str, tuple[str, ...]] = {
    "standard": ("standard",),
    "ev": ("ev", "standard"),
    "accessible": ("accessible", "standard"),
}


class ConfigError(ValueError):
    """Raised for invalid / malformed configuration or input data."""


@dataclass
class CarParkConfig:
    name: str
    standard: int = 60
    ev: int = 6
    accessible: int = 4
    gate_distance_m: float = 300.0  # drive: campus entrance -> car-park entrance
    walk_base_m: float = 250.0  # walk: car-park entrance -> destination building
    pitch_m: float = 4.0  # distance added per space position along the aisle

    @property
    def capacity(self) -> int:
        return self.standard + self.ev + self.accessible


def _default_car_parks() -> list[CarParkConfig]:
    return [
        CarParkConfig("North Car Park", 70, 8, 4, gate_distance_m=250, walk_base_m=420),
        CarParkConfig("Central Car Park", 50, 6, 4, gate_distance_m=450, walk_base_m=200),
        CarParkConfig("Multi-storey", 90, 10, 6, gate_distance_m=650, walk_base_m=90),
    ]


@dataclass
class ScenarioConfig:
    name: str = "moderate"
    description: str = "Moderate demand with two daily peaks (synthetic)."
    seed: int = 42
    duration_min: int = 720  # observation window; minute 0 = start of the day
    sample_interval_min: int = 10
    # --- demand model (synthetic) ---
    base_arrivals_per_hour: float = 60.0
    peak_factor: float = 1.8  # 1.0 = flat demand
    peak_times_min: list[float] = field(default_factory=lambda: [120.0, 420.0])
    peak_width_min: float = 60.0  # sd of the Gaussian demand bumps
    demand_variation: float = 0.15  # sd of hourly lognormal demand multiplier
    mean_duration_min: float = 180.0
    duration_cv: float = 0.8  # coefficient of variation of parking duration
    min_duration_min: float = 15.0
    max_duration_min: float = 600.0
    ev_share: float = 0.12
    accessible_share: float = 0.04
    patience_mean_min: float = 10.0  # 0 => a vehicle that cannot park leaves at once
    walk_pref_min_m: float = 500.0  # vehicles refuse offers beyond their own walk limit
    walk_pref_max_m: float = 1500.0
    # --- car parks ---
    car_parks: list[CarParkConfig] = field(default_factory=_default_car_parks)
    # --- strategy parameters (coordinated strategy; units = "metre-equivalents") ---
    w_drive: float = 1.0
    w_walk: float = 1.5
    w_congestion: float = 300.0  # penalty per unit occupancy ratio of the car park
    ev_bonus: float = 400.0  # credit for putting an EV in an EV bay
    accessible_bonus: float = 400.0
    accessible_walk_multiplier: float = 3.0
    # --- emission proxy assumptions (illustrative, NOT measured) ---
    emission_g_per_km: float = 150.0
    idle_g_per_min: float = 20.0

    @property
    def total_capacity(self) -> int:
        return sum(cp.capacity for cp in self.car_parks)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> ScenarioConfig:
        validate_config(self)
        return self


def _num(cond: bool, msg: str, errors: list[str]) -> None:
    if not cond:
        errors.append(msg)


def validate_config(cfg: ScenarioConfig) -> None:
    """Raise :class:`ConfigError` listing *all* problems found."""
    e: list[str] = []
    _num(isinstance(cfg.seed, int) and not isinstance(cfg.seed, bool) and cfg.seed >= 0,
         "seed must be a non-negative integer", e)
    _num(isinstance(cfg.duration_min, (int, float)) and cfg.duration_min > 0,
         "duration_min must be > 0", e)
    _num(cfg.sample_interval_min > 0, "sample_interval_min must be > 0", e)
    _num(cfg.base_arrivals_per_hour >= 0, "base_arrivals_per_hour must be >= 0 (0 = zero demand)", e)
    _num(cfg.peak_factor >= 1.0, "peak_factor must be >= 1.0 (1.0 = flat demand)", e)
    _num(cfg.peak_width_min > 0, "peak_width_min must be > 0", e)
    _num(0.0 <= cfg.demand_variation <= 1.0, "demand_variation must be in [0, 1]", e)
    _num(cfg.mean_duration_min > 0, "mean_duration_min must be > 0", e)
    _num(cfg.duration_cv >= 0, "duration_cv must be >= 0", e)
    _num(0 < cfg.min_duration_min <= cfg.max_duration_min, "need 0 < min_duration_min <= max_duration_min", e)
    _num(cfg.min_duration_min <= cfg.mean_duration_min <= cfg.max_duration_min or cfg.duration_cv == 0,
         "mean_duration_min should lie between min_duration_min and max_duration_min", e)
    _num(0 <= cfg.ev_share <= 1 and 0 <= cfg.accessible_share <= 1 and cfg.ev_share + cfg.accessible_share <= 1,
         "ev_share and accessible_share must be in [0,1] and sum to <= 1", e)
    _num(cfg.patience_mean_min >= 0, "patience_mean_min must be >= 0", e)
    _num(0 < cfg.walk_pref_min_m <= cfg.walk_pref_max_m, "need 0 < walk_pref_min_m <= walk_pref_max_m", e)
    for name in ("w_drive", "w_walk", "w_congestion", "ev_bonus", "accessible_bonus",
                 "accessible_walk_multiplier", "emission_g_per_km", "idle_g_per_min"):
        _num(getattr(cfg, name) >= 0, f"{name} must be >= 0", e)
    if not cfg.car_parks:
        e.append("at least one car park is required")
    names = [cp.name for cp in cfg.car_parks]
    _num(len(set(names)) == len(names), "car park names must be unique", e)
    for cp in cfg.car_parks:
        for attr in ("standard", "ev", "accessible"):
            v = getattr(cp, attr)
            _num(isinstance(v, int) and not isinstance(v, bool) and v >= 0,
                 f"car park '{cp.name}': {attr} must be a non-negative integer", e)
        if all(isinstance(getattr(cp, a), int) for a in ("standard", "ev", "accessible")):
            _num(cp.capacity > 0, f"car park '{cp.name}': capacity must be > 0", e)
        _num(cp.gate_distance_m >= 0 and cp.walk_base_m >= 0, f"car park '{cp.name}': distances must be >= 0", e)
        _num(cp.pitch_m > 0, f"car park '{cp.name}': pitch_m must be > 0", e)
    if e:
        raise ConfigError("Invalid configuration:\n - " + "\n - ".join(e))


def config_from_dict(d: dict[str, Any]) -> ScenarioConfig:
    """Build and validate a config from a plain dict (e.g. parsed JSON)."""
    if not isinstance(d, dict):
        raise ConfigError("configuration must be a JSON object")
    known = {f.name for f in fields(ScenarioConfig)}
    unknown = set(d) - known
    if unknown:
        raise ConfigError(f"unknown configuration field(s): {sorted(unknown)}")
    d = dict(d)
    try:
        if "car_parks" in d:
            if not isinstance(d["car_parks"], list):
                raise ConfigError("car_parks must be a list")
            d["car_parks"] = [CarParkConfig(**cp) for cp in d["car_parks"]]
        cfg = ScenarioConfig(**d)
    except TypeError as exc:
        raise ConfigError(f"malformed configuration: {exc}") from exc
    return cfg.validate()


def load_config(path: str | Path) -> ScenarioConfig:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"configuration file is not valid JSON: {p} ({exc})") from exc
    return config_from_dict(data)


def save_config(cfg: ScenarioConfig, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# predefined scenarios
# --------------------------------------------------------------------------- #
def _scaled(name: str, desc: str, **kw: Any) -> ScenarioConfig:
    return ScenarioConfig(name=name, description=desc, **kw)


def predefined_scenarios() -> dict[str, ScenarioConfig]:
    s = [
        _scaled("low_demand", "Low demand: car parks rarely approach capacity (synthetic).",
                base_arrivals_per_hour=25, peak_factor=1.3),
        _scaled("moderate_demand", "Moderate demand with two mild peaks (synthetic).",
                base_arrivals_per_hour=50, peak_factor=1.6),
        _scaled("high_demand", "High demand: sustained pressure on capacity (synthetic).",
                base_arrivals_per_hour=85, peak_factor=1.6),
        _scaled("peak_arrivals", "Sharp, narrow arrival peaks (synthetic).",
                base_arrivals_per_hour=55, peak_factor=3.0, peak_width_min=30),
        _scaled("long_stays", "Moderate demand with long parking durations (synthetic).",
                base_arrivals_per_hour=40, peak_factor=1.5, mean_duration_min=300, duration_cv=0.6),
        _scaled("volatile_demand", "Moderate demand with strong hour-to-hour variation (synthetic).",
                base_arrivals_per_hour=55, peak_factor=1.5, demand_variation=0.6),
        _scaled("small_capacity", "High demand against reduced capacity (synthetic).",
                base_arrivals_per_hour=60, peak_factor=1.6,
                car_parks=[CarParkConfig("North Car Park", 35, 4, 2, 250, 420),
                           CarParkConfig("Central Car Park", 30, 3, 2, 450, 200),
                           CarParkConfig("Multi-storey", 45, 5, 3, 650, 90)]),
    ]
    return {c.name: c for c in s}


def write_scenario_files(directory: str | Path) -> list[Path]:
    out = []
    for name, cfg in predefined_scenarios().items():
        p = Path(directory) / f"{name}.json"
        save_config(cfg, p)
        out.append(p)
    return out

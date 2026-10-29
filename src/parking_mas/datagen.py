"""Deterministic synthetic arrival generator (NOT real data).

Arrivals follow a non-homogeneous Poisson process (Lewis-Shedler thinning):

    rate(t) = base/60 * (1 + (peak_factor-1) * bump(t)) * hourly_multiplier(t)   [vehicles/min]

bump(t) = max over peak_times of exp(-0.5 ((t - p)/peak_width)^2);
hourly_multiplier ~ lognormal with mean 1 and sd ~ demand_variation (one draw per hour).
Durations are lognormal (mean, cv) clipped to [min, max]; vehicle types are
categorical; walking limits are uniform.  Independent random sub-streams are
spawned from the seed so the arrival stream does not depend on the strategy.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from .config import VEHICLE_TYPES, ConfigError, ScenarioConfig

ARRIVAL_COLUMNS = ["vehicle_id", "arrival_min", "duration_min", "vehicle_type", "patience_min", "max_walk_m"]


def _rate_fn(cfg: ScenarioConfig, hourly: np.ndarray):
    peaks = np.asarray(cfg.peak_times_min, dtype=float)

    def rate(t: float) -> float:
        bump = float(np.max(np.exp(-0.5 * ((t - peaks) / cfg.peak_width_min) ** 2))) if peaks.size else 0.0
        h = hourly[min(int(t // 60), len(hourly) - 1)]
        return cfg.base_arrivals_per_hour / 60.0 * (1 + (cfg.peak_factor - 1) * bump) * h

    return rate


def generate_arrivals(cfg: ScenarioConfig, seed: int | None = None) -> pd.DataFrame:
    """Return a DataFrame with :data:`ARRIVAL_COLUMNS`, sorted by arrival time."""
    cfg.validate()
    seed = cfg.seed if seed is None else seed
    ss = np.random.SeedSequence(seed)
    r_time, r_hour, r_attr = (np.random.default_rng(s) for s in ss.spawn(3))
    n_hours = int(math.ceil(cfg.duration_min / 60))
    v = cfg.demand_variation
    hourly = r_hour.lognormal(-0.5 * v * v, v, n_hours) if v > 0 else np.ones(n_hours)
    if cfg.base_arrivals_per_hour == 0:
        return pd.DataFrame(columns=ARRIVAL_COLUMNS)
    rate = _rate_fn(cfg, hourly)
    lam_max = cfg.base_arrivals_per_hour / 60.0 * cfg.peak_factor * float(hourly.max())
    times: list[float] = []
    t = 0.0
    while True:
        t += r_time.exponential(1.0 / lam_max)
        if t >= cfg.duration_min:
            break
        if r_time.random() < rate(t) / lam_max:
            times.append(t)
    n = len(times)
    if cfg.duration_cv > 0:
        sigma2 = math.log(1 + cfg.duration_cv ** 2)
        dur = r_attr.lognormal(math.log(cfg.mean_duration_min) - sigma2 / 2, math.sqrt(sigma2), n)
    else:
        dur = np.full(n, cfg.mean_duration_min)
    dur = np.clip(dur, cfg.min_duration_min, cfg.max_duration_min)
    p = [1 - cfg.ev_share - cfg.accessible_share, cfg.ev_share, cfg.accessible_share]
    vtype = r_attr.choice(VEHICLE_TYPES, size=n, p=p)
    patience = r_attr.exponential(cfg.patience_mean_min, n) if cfg.patience_mean_min > 0 else np.zeros(n)
    walk = r_attr.uniform(cfg.walk_pref_min_m, cfg.walk_pref_max_m, n)
    walk = np.where(vtype == "accessible", walk * 0.5, walk)  # tighter limit for accessible permit holders
    return pd.DataFrame({
        "vehicle_id": [f"V{i:05d}" for i in range(n)],
        "arrival_min": np.round(times, 3),
        "duration_min": np.round(dur, 2),
        "vehicle_type": vtype,
        "patience_min": np.round(patience, 2),
        "max_walk_m": np.round(walk, 1),
    })


def save_arrivals(df: pd.DataFrame, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)


def load_arrivals(path: str | Path) -> pd.DataFrame:
    """Load an arrivals CSV.  Structural problems raise; bad *values* are kept and
    later counted as invalid requests by the engine."""
    p = Path(path)
    try:
        df = pd.read_csv(p)
    except FileNotFoundError as exc:
        raise ConfigError(f"arrivals file not found: {p}") from exc
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise ConfigError(f"arrivals file is malformed: {p} ({exc})") from exc
    missing = [c for c in ARRIVAL_COLUMNS if c not in df.columns]
    if missing:
        raise ConfigError(f"arrivals file missing column(s): {missing}")
    return df[ARRIVAL_COLUMNS].sort_values("arrival_min", kind="stable").reset_index(drop=True)

"""Metric definitions (see docs/metrics.md for numerator/denominator/unit/window).

Observation window: simulated minutes [0, duration_min].  A *valid request* is a
request with valid fields that arrives inside the window.  Every valid request ends
the window in exactly one state: served, failed or pending, so
success_rate + failed_rate + pending_rate = 1.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import ScenarioConfig
from .engine import Simulation


def _safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b else float("nan")


def compute_metrics(sim: Simulation) -> dict[str, Any]:
    """Compute all run-level metrics from a (finished) simulation."""
    cfg: ScenarioConfig = sim.cfg
    vt = sim.vehicle_table()
    valid = vt[vt["status"] != "invalid"] if not vt.empty else vt
    n_valid = len(valid)
    served = valid[valid["status"] == "served"] if n_valid else valid
    failed = valid[valid["status"] == "failed"] if n_valid else valid
    pending = valid[valid["status"] == "pending"] if n_valid else valid
    area, area_cp = sim.occupancy_area
    cap = sim.manager.capacity
    horizon = sim.horizon
    m: dict[str, Any] = {
        "strategy": sim.strategy_name,
        "scenario": cfg.name,
        "seed": cfg.seed,
        "total_capacity": cap,
        "valid_requests": n_valid,
        "invalid_requests": int((vt["status"] == "invalid").sum()) if not vt.empty else 0,
        "successful_requests": len(served),
        "failed_requests": len(failed),
        "pending_requests": len(pending),
        "success_rate": _safe_div(len(served), n_valid),
        "failed_rate": _safe_div(len(failed), n_valid),
        "pending_rate": _safe_div(len(pending), n_valid),
        "immediate_allocation_rate": _safe_div(int((served["waited_min"] == 0).sum()) if len(served) else 0, n_valid),
        "utilisation": _safe_div(area, cap * horizon),
    }
    s = pd.DataFrame(sim.samples)
    m["peak_occupancy_ratio"] = float(s["occupancy_ratio"].max()) if not s.empty else float("nan")
    m["mean_queue_length"] = float(s["queue_length"].mean()) if not s.empty else float("nan")
    waits = served["waited_min"].to_numpy(float) if len(served) else np.array([])
    m["mean_wait_min"] = float(waits.mean()) if waits.size else float("nan")
    m["p95_wait_min"] = float(np.percentile(waits, 95)) if waits.size else float("nan")
    # total idle time of every valid request (served, failed or pending) feeds the emission proxy
    total_wait = float(valid["waited_min"].sum()) if n_valid else 0.0
    m["mean_decision_ms"] = (float(np.mean([d["compute_us"] for d in sim.decisions])) / 1000.0
                             if sim.decisions else float("nan"))
    m["mean_drive_m"] = float(served["drive_m"].mean()) if len(served) else float("nan")
    m["mean_walk_m"] = float(served["walk_m"].mean()) if len(served) else float("nan")
    total_drive_km = float(served["drive_m"].sum()) / 1000.0 if len(served) else 0.0
    m["total_drive_km"] = total_drive_km
    m["total_wait_min"] = total_wait
    # simulation-based proxy ONLY - see docs/metrics.md
    m["co2e_proxy_kg"] = (total_drive_km * cfg.emission_g_per_km + total_wait * cfg.idle_g_per_min) / 1000.0
    m["co2e_proxy_g_per_request"] = _safe_div(m["co2e_proxy_kg"] * 1000.0, n_valid)
    ev = served[served["vehicle_type"] == "ev"] if len(served) else served
    m["ev_bay_match_rate"] = (_safe_div(int((ev["space_type"] == "ev").sum()), len(ev)) if len(ev) else float("nan"))
    for reason in ("no_wait", "timeout_full", "timeout_declined"):
        m[f"fail_{reason}"] = int((failed["fail_reason"] == reason).sum()) if len(failed) else 0
    for cp in sim.car_parks:
        m[f"util_{cp.name}"] = _safe_div(area_cp[cp.name], cp.capacity * horizon)
        m[f"alloc_{cp.name}"] = int((served["car_park"] == cp.name).sum()) if len(served) else 0
        m[f"alloc_share_{cp.name}"] = _safe_div(m[f"alloc_{cp.name}"], len(served))
    m["messages_total"] = sim.bus.total
    return m


def occupancy_timeseries(sim: Simulation) -> pd.DataFrame:
    return pd.DataFrame(sim.samples)

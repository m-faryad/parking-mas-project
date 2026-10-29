import pandas as pd

from parking_mas.config import CarParkConfig, ScenarioConfig


def tiny_cfg(**kw) -> ScenarioConfig:
    base = dict(name="tiny", duration_min=120, base_arrivals_per_hour=30, peak_factor=1.0, demand_variation=0.0,
                mean_duration_min=60, duration_cv=0.0, patience_mean_min=0.0, sample_interval_min=10,
                car_parks=[CarParkConfig("A", 2, 1, 1, 100, 300), CarParkConfig("B", 2, 0, 0, 200, 100)])
    base.update(kw)
    return ScenarioConfig(**base)


def arrivals(rows) -> pd.DataFrame:
    """rows: (id, arrival, duration, type, patience, max_walk)"""
    return pd.DataFrame(rows, columns=["vehicle_id", "arrival_min", "duration_min", "vehicle_type",
                                       "patience_min", "max_walk_m"])

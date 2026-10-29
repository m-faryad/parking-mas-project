import math

import pytest
from helpers import arrivals, tiny_cfg

from parking_mas.config import CarParkConfig
from parking_mas.engine import Simulation
from parking_mas.metrics import compute_metrics


def run(cfg, rows, strategy="baseline"):
    sim = Simulation(cfg, strategy, arrivals=arrivals(rows)).run()
    return sim, compute_metrics(sim)


def test_full_lifecycle_and_utilisation_exact():
    # one vehicle parks 60 min of a 120 min window in a 6-space system
    sim, m = run(tiny_cfg(), [("V1", 10, 60, "standard", 0, 5000)])
    assert m["successful_requests"] == 1 and m["success_rate"] == 1.0
    assert m["utilisation"] == pytest.approx(60 / (6 * 120))
    assert sim.manager.occupied == 0  # departed at 70
    assert [e["event"] for e in sim.events if e["vehicle_id"] == "V1"] == ["request", "allocate", "depart"]


def test_departure_frees_space_for_waiting_vehicle():
    cfg = tiny_cfg(car_parks=[CarParkConfig("A", 1, 0, 0, 100, 100)], patience_mean_min=10)
    sim, m = run(cfg, [("V1", 0, 30, "standard", 0, 5000), ("V2", 5, 30, "standard", 50, 5000)])
    assert m["successful_requests"] == 2 and m["mean_wait_min"] == pytest.approx(12.5)  # (0 + 25)/2
    assert sim.vehicle_table().set_index("vehicle_id").loc["V2", "space_id"] == sim.vehicle_table().set_index("vehicle_id").loc["V1", "space_id"]


def test_failed_and_pending_accounting_sums_to_one():
    cfg = tiny_cfg(car_parks=[CarParkConfig("A", 1, 0, 0, 100, 100)], duration_min=100)
    rows = [("V1", 0, 500, "standard", 0, 5000), ("V2", 1, 30, "standard", 0, 5000),
            ("V3", 2, 30, "standard", 20, 5000), ("V4", 95, 30, "standard", 50, 5000)]
    sim, m = run(cfg, rows)
    assert (m["successful_requests"], m["failed_requests"], m["pending_requests"]) == (1, 2, 1)
    assert m["success_rate"] + m["failed_rate"] + m["pending_rate"] == pytest.approx(1.0)
    assert m["fail_no_wait"] == 1 and m["fail_timeout_full"] == 1


def test_invalid_requests_excluded_from_denominator():
    rows = [("V1", 0, 30, "standard", 0, 5000), ("V2", 1, -5, "standard", 0, 5000), ("V3", 2, 30, "truck", 0, 5000),
            ("V4", 3, float("nan"), "standard", 0, 5000)]
    sim, m = run(tiny_cfg(), rows)
    assert m["valid_requests"] == 1 and m["invalid_requests"] == 3 and m["success_rate"] == 1.0


def test_zero_demand():
    sim, m = run(tiny_cfg(), [])
    assert m["valid_requests"] == 0 and m["utilisation"] == 0 and math.isnan(m["success_rate"])


def test_capacity_never_exceeded_under_heavy_load():
    cfg = tiny_cfg(base_arrivals_per_hour=600, patience_mean_min=5, duration_min=300)
    sim = Simulation(cfg, "coordinated")
    t = 0
    while not sim.finished:
        t += 7
        sim.step(t)
        assert sim.manager.occupied <= sim.manager.capacity
        sim.manager.check_invariants()
    assert max(s["occupied"] for s in sim.samples) <= sim.manager.capacity


def test_no_space_holds_two_vehicles_in_history():
    cfg = tiny_cfg(base_arrivals_per_hour=300, patience_mean_min=5, duration_min=300, duration_cv=0.5)
    sim = Simulation(cfg, "baseline").run()
    for cp in sim.car_parks:
        for s in cp.spaces:
            held = None
            for _, ev, vid in s.history:
                if ev == "occupy":
                    assert held is None
                    held = vid
                else:
                    assert held == vid
                    held = None


def test_decision_log_explains_choice_and_failure():
    cfg = tiny_cfg(car_parks=[CarParkConfig("A", 1, 0, 0, 100, 100)])
    sim, _ = run(cfg, [("V1", 0, 30, "standard", 0, 5000), ("V2", 1, 30, "standard", 0, 5000)], "coordinated")
    d = {r["vehicle_id"]: r for r in sim.decisions}
    assert d["V1"]["outcome"] == "allocated" and "weighted cost" in d["V1"]["reason"] and d["V1"]["candidates"]
    assert d["V2"]["outcome"] == "not_allocated" and d["V2"]["reason"] == "no eligible space free"


def test_step_is_incremental_and_equals_run():
    cfg = tiny_cfg(base_arrivals_per_hour=100, duration_min=240)
    a = Simulation(cfg, "coordinated").run()
    b = Simulation(cfg, "coordinated")
    for t in range(15, 241, 15):
        b.step(t)
    assert [d["space_id"] for d in a.decisions] == [d["space_id"] for d in b.decisions]


def test_same_seed_is_reproducible_and_strategies_share_arrivals():
    cfg = tiny_cfg(base_arrivals_per_hour=120, patience_mean_min=5, duration_cv=0.5, ev_share=0.2)
    m1 = compute_metrics(Simulation(cfg, "coordinated").run())
    m2 = compute_metrics(Simulation(cfg, "coordinated").run())
    skip = {"mean_decision_ms"}
    for k in m1:
        if k not in skip and not (isinstance(m1[k], float) and math.isnan(m1[k])):
            assert m1[k] == m2[k], k
    assert Simulation(cfg, "baseline").arrivals.equals(Simulation(cfg, "coordinated").arrivals)


def test_emission_proxy_formula_and_missing_values():
    cfg = tiny_cfg(emission_g_per_km=100, idle_g_per_min=10, car_parks=[CarParkConfig("A", 1, 0, 0, 1000, 100, 4)])
    sim, m = run(cfg, [("V1", 0, 30, "standard", 0, 5000)])
    assert m["total_drive_km"] == pytest.approx(1.0) and m["co2e_proxy_kg"] == pytest.approx(0.1)
    assert math.isnan(m["ev_bay_match_rate"])  # no EVs: undefined, not zero


def test_p95_wait_and_mean_wait():
    cfg = tiny_cfg(car_parks=[CarParkConfig("A", 1, 0, 0, 100, 100)])
    rows = [("V1", 0, 10, "standard", 0, 5000), ("V2", 1, 10, "standard", 20, 5000)]
    _, m = run(cfg, rows)
    assert m["mean_wait_min"] == pytest.approx(4.5) and m["p95_wait_min"] == pytest.approx(8.55)

import json
import math

import pandas as pd
import pytest
from helpers import tiny_cfg

from parking_mas import analytics, cli
from parking_mas.config import CarParkConfig, ConfigError, config_from_dict, load_config, predefined_scenarios, save_config
from parking_mas.datagen import generate_arrivals, load_arrivals, save_arrivals
from parking_mas.experiment import run_experiment, seed_for


# ----- configuration
def test_predefined_scenarios_valid():
    for c in predefined_scenarios().values():
        c.validate()


@pytest.mark.parametrize("change", [dict(duration_min=0), dict(seed=-1), dict(peak_factor=0.5), dict(ev_share=0.8, accessible_share=0.5),
                                    dict(base_arrivals_per_hour=-1), dict(min_duration_min=0), dict(car_parks=[]),
                                    dict(demand_variation=2), dict(patience_mean_min=-1)])
def test_invalid_config_rejected(change):
    with pytest.raises(ConfigError):
        tiny_cfg(**change).validate()


def test_invalid_car_parks():
    with pytest.raises(ConfigError, match="capacity"):
        tiny_cfg(car_parks=[CarParkConfig("Z", 0, 0, 0)]).validate()
    with pytest.raises(ConfigError, match="unique"):
        tiny_cfg(car_parks=[CarParkConfig("Z", 1), CarParkConfig("Z", 1)]).validate()
    with pytest.raises(ConfigError):
        tiny_cfg(car_parks=[CarParkConfig("Z", -3)]).validate()


def test_all_errors_reported_together():
    with pytest.raises(ConfigError) as e:
        tiny_cfg(duration_min=-1, seed=-2).validate()
    assert "duration_min" in str(e.value) and "seed" in str(e.value)


def test_config_roundtrip_with_spaces_in_path(tmp_path):
    p = tmp_path / "my folder" / "cfg file.json"
    cfg = predefined_scenarios()["high_demand"]
    save_config(cfg, p)
    assert load_config(p).to_dict() == cfg.to_dict()


def test_malformed_and_missing_config(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ConfigError):
        load_config(bad)
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.json")
    with pytest.raises(ConfigError, match="unknown"):
        config_from_dict({"nonsense": 1})
    with pytest.raises(ConfigError):
        config_from_dict([1, 2])
    with pytest.raises(ConfigError):
        config_from_dict({"car_parks": [{"oops": 1}]})


# ----- synthetic data
def test_generator_deterministic_and_seed_sensitive():
    cfg = predefined_scenarios()["moderate_demand"]
    a, b = generate_arrivals(cfg), generate_arrivals(cfg)
    assert a.equals(b)
    c = generate_arrivals(cfg, seed=cfg.seed + 1)
    assert not a.equals(c)


def test_generator_properties():
    cfg = predefined_scenarios()["moderate_demand"]
    df = generate_arrivals(cfg)
    assert df.arrival_min.is_monotonic_increasing and df.arrival_min.between(0, cfg.duration_min).all()
    assert df.duration_min.between(cfg.min_duration_min, cfg.max_duration_min).all()
    assert set(df.vehicle_type) <= {"standard", "ev", "accessible"}
    assert df.vehicle_id.is_unique
    assert abs((df.vehicle_type == "ev").mean() - cfg.ev_share) < 0.05


def test_demand_scales_with_rate_and_zero_demand():
    lo = len(generate_arrivals(tiny_cfg(base_arrivals_per_hour=20)))
    hi = len(generate_arrivals(tiny_cfg(base_arrivals_per_hour=200)))
    assert hi > 4 * lo
    assert generate_arrivals(tiny_cfg(base_arrivals_per_hour=0)).empty


def test_peak_factor_concentrates_arrivals():
    cfg = tiny_cfg(duration_min=720, base_arrivals_per_hour=60, peak_factor=4.0, peak_times_min=[120.0], peak_width_min=20)
    df = generate_arrivals(cfg)
    near = df.arrival_min.between(90, 150).sum() / 60
    far = df.arrival_min.between(500, 560).sum() / 60
    assert near > 2 * far


def test_arrivals_csv_roundtrip_and_errors(tmp_path):
    df = generate_arrivals(tiny_cfg())
    p = tmp_path / "a b" / "arr.csv"
    save_arrivals(df, p)
    pd.testing.assert_frame_equal(load_arrivals(p), df.sort_values("arrival_min", kind="stable").reset_index(drop=True), check_dtype=False)
    with pytest.raises(ConfigError):
        load_arrivals(tmp_path / "none.csv")
    (tmp_path / "x.csv").write_text("a,b\n1,2\n")
    with pytest.raises(ConfigError, match="missing"):
        load_arrivals(tmp_path / "x.csv")
    (tmp_path / "empty.csv").write_text("")
    with pytest.raises(ConfigError):
        load_arrivals(tmp_path / "empty.csv")


def test_bundled_sample_loads():
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "data" / "sample" / "sample_arrivals.csv"
    assert len(load_arrivals(p)) > 0


# ----- experiments / analytics
@pytest.fixture(scope="module")
def results(tmp_path_factory):
    out = tmp_path_factory.mktemp("res dir") / "exp"
    scs = [predefined_scenarios()["moderate_demand"], predefined_scenarios()["high_demand"]]
    for s in scs:
        s.duration_min = 240
    run_experiment(scs, 6, 11, out, mode="test")
    return out


def test_experiment_persists_expected_files_and_schema(results):
    for f in ("runs.csv", "occupancy_timeseries.csv", "metadata.json", "decision_log_replication0.csv"):
        assert (results / f).exists()
    runs = pd.read_csv(results / "runs.csv")
    assert len(runs) == 2 * 6 * 2
    assert {"scenario", "strategy", "replication", "seed", "success_rate", "utilisation"} <= set(runs.columns)
    meta = json.loads((results / "metadata.json").read_text())
    assert "SYNTHETIC" in meta["data_origin"] and meta["replications"] == 6


def test_paired_runs_share_seed_and_demand(results):
    runs = pd.read_csv(results / "runs.csv")
    p = runs.pivot_table(index=["scenario", "seed"], columns="strategy", values="valid_requests")
    assert (p["baseline"] == p["coordinated"]).all()
    assert runs.seed.iloc[0] == seed_for(11, 0, 0)


def test_experiment_reproducible(results, tmp_path):
    scs = [predefined_scenarios()["moderate_demand"], predefined_scenarios()["high_demand"]]
    for s in scs:
        s.duration_min = 240
    run_experiment(scs, 6, 11, tmp_path / "again", mode="test")
    a, b = pd.read_csv(results / "runs.csv"), pd.read_csv(tmp_path / "again" / "runs.csv")
    cols = [c for c in a.columns if c not in ("wall_clock_s", "mean_decision_ms")]
    pd.testing.assert_frame_equal(a[cols], b[cols])


def test_no_silent_overwrite(results):
    with pytest.raises(FileExistsError):
        run_experiment([tiny_cfg()], 2, 1, results)


def test_experiment_input_validation(tmp_path):
    with pytest.raises(ConfigError):
        run_experiment([tiny_cfg()], 0, 1, tmp_path / "x")
    with pytest.raises(ConfigError):
        run_experiment([], 2, 1, tmp_path / "y")


def test_analytics_reads_persisted_results_and_writes_outputs(results):
    files = analytics.analyse(results)
    for k in ("summary", "comparison", "tables_md", "occupancy_over_time", "strategy_comparison"):
        assert files[k].exists() and files[k].stat().st_size > 0
    comp = pd.read_csv(files["comparison"])
    row = comp[(comp.scenario == "high_demand") & (comp.metric == "success_rate")].iloc[0]
    runs = pd.read_csv(results / "runs.csv")
    g = runs[runs.scenario == "high_demand"].pivot(index="seed", columns="strategy", values="success_rate")
    assert row.mean_diff == pytest.approx((g["coordinated"] - g["baseline"]).mean())
    assert row.n_pairs == 6


def test_compare_handles_identical_and_tiny_samples():
    runs = pd.DataFrame({"scenario": ["s"] * 4, "strategy": ["baseline", "coordinated"] * 2, "seed": [1, 1, 2, 2],
                         "success_rate": [1.0, 1.0, 1.0, 1.0], "valid_requests": [10] * 4})
    c = analytics.compare_strategies(runs, ["success_rate"]).iloc[0]
    assert c.note == "no difference in any pair" and math.isnan(c.p_ttest)
    one = runs.iloc[:2]
    assert "fewer than 2" in analytics.compare_strategies(one, ["success_rate"]).iloc[0].note


def test_missing_optional_metric_columns_are_tolerated():
    runs = pd.DataFrame({"scenario": ["s"] * 4, "strategy": ["baseline", "coordinated"] * 2, "seed": [1, 1, 2, 2],
                         "success_rate": [0.9, 0.95, 0.8, 0.9]})
    assert not analytics.summarise(runs).empty  # co2e etc. absent -> skipped
    assert analytics.compare_strategies(runs).metric.tolist() == ["success_rate"]


def test_load_results_errors(tmp_path):
    with pytest.raises(analytics.ResultsError):
        analytics.load_results(tmp_path)
    (tmp_path / "runs.csv").write_text("scenario\n")
    (tmp_path / "occupancy_timeseries.csv").write_text("x\n")
    (tmp_path / "metadata.json").write_text("{}")
    with pytest.raises(analytics.ResultsError, match="empty"):
        analytics.load_results(tmp_path)


def test_holm_adjustment():
    adj = analytics._holm([0.01, 0.04, float("nan"), 0.03])
    assert adj[0] == pytest.approx(0.03) and adj[3] == pytest.approx(0.06) and adj[1] == pytest.approx(0.06) and math.isnan(adj[2])


def test_cli_run_check_and_existing_results(results, tmp_path, capsys):
    assert cli.main(["run", "--scenario", "low_demand", "--strategy", "baseline", "--seed", "3"]) == 0
    assert '"success_rate"' in capsys.readouterr().out
    assert cli.main(["run", "--config", str(tmp_path / "nope.json")]) == 2
    assert cli.main(["experiment", "--out", str(results)]) == 3  # refuses to overwrite
    assert cli.main(["experiment", "--out", str(results), "--skip-existing"]) == 0
    assert cli.main(["analyse", str(results)]) == 0

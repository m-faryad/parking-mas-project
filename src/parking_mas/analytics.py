"""Analytics: load saved experiment results, aggregate, compare strategies, draw figures.

Everything here reads files written by :func:`parking_mas.experiment.run_experiment`;
no value is hard-coded.  Strategy pairs are compared *paired by seed*.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

# metric -> (label, unit, direction) ; direction: +1 higher is better, -1 lower is better, 0 neutral
METRICS: dict[str, tuple[str, str, int]] = {
    "success_rate": ("Successful parking rate", "share of valid requests", 1),
    "failed_rate": ("Failed parking rate", "share of valid requests", -1),
    "utilisation": ("Space utilisation", "share of space-minutes", 0),
    "mean_wait_min": ("Mean waiting time (served)", "simulated min", -1),
    "p95_wait_min": ("95th-pct waiting time (served)", "simulated min", -1),
    "mean_drive_m": ("Mean drive distance", "m", -1),
    "mean_walk_m": ("Mean walk distance", "m", -1),
    "co2e_proxy_kg": ("CO2e proxy (drive + idle)", "kg, simulation estimate", -1),
    "ev_bay_match_rate": ("EV vehicles in EV bays", "share of served EVs", 1),
    "mean_decision_ms": ("Mean decision compute time", "ms wall-clock", -1),
}
BASE, SMART = "baseline", "coordinated"
STYLE = {BASE: dict(color="#0072B2", marker="o", ls="--", hatch="//"),
         SMART: dict(color="#D55E00", marker="s", ls="-", hatch="")}
SYNTH_NOTE = "Synthetic simulation data - not measured at any real car park."


class ResultsError(RuntimeError):
    pass


def load_results(results_dir: str | Path) -> dict:
    d = Path(results_dir)
    need = ["runs.csv", "occupancy_timeseries.csv", "metadata.json"]
    missing = [n for n in need if not (d / n).exists()]
    if missing:
        raise ResultsError(f"{d} is not a complete results folder; missing {missing}")
    runs = pd.read_csv(d / "runs.csv")
    if runs.empty:
        raise ResultsError(f"{d / 'runs.csv'} is empty")
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
    occ = pd.read_csv(d / "occupancy_timeseries.csv")
    dec_path = d / "decision_log_replication0.csv"
    dec = pd.read_csv(dec_path) if dec_path.exists() else pd.DataFrame()
    return {"runs": runs, "occupancy": occ, "meta": meta, "decisions": dec, "dir": d}


def _ci(x: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return (float("nan"), float("nan"))
    h = stats.sem(x) * stats.t.ppf((1 + level) / 2, len(x) - 1)
    return (float(x.mean() - h), float(x.mean() + h))


def summarise(runs: pd.DataFrame, metrics: list[str] | None = None) -> pd.DataFrame:
    """Mean, sd, 95% t-CI and n per scenario x strategy x metric (long format)."""
    metrics = [m for m in (metrics or list(METRICS)) if m in runs.columns]
    rows = []
    for (sc, st), g in runs.groupby(["scenario", "strategy"], sort=False):
        for m in metrics:
            x = g[m].to_numpy(float)
            lo, hi = _ci(x)
            n = int((~np.isnan(x)).sum())
            rows.append({"scenario": sc, "strategy": st, "metric": m, "n": n,
                         "mean": float(np.nanmean(x)) if n else float("nan"),
                         "sd": float(np.nanstd(x, ddof=1)) if n > 1 else float("nan"),
                         "ci95_low": lo, "ci95_high": hi})
    return pd.DataFrame(rows)


def _holm(p: list[float]) -> list[float]:
    idx = [i for i, v in enumerate(p) if not math.isnan(v)]
    order = sorted(idx, key=lambda i: p[i])
    adj = [float("nan")] * len(p)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (len(order) - rank) * p[i])
        adj[i] = min(1.0, running)
    return adj


def compare_strategies(runs: pd.DataFrame, metrics: list[str] | None = None) -> pd.DataFrame:
    """Paired (by seed) comparison coordinated - baseline for each scenario and metric.

    Reports the mean paired difference with a 95% t-interval, Cohen's d_z, a paired
    t-test and a Wilcoxon signed-rank test, plus Holm-adjusted t-test p-values across
    the metrics of a scenario.  Tests are descriptive: runs are simulated, so
    "significance" depends on the number of replications the analyst chooses.
    """
    metrics = [m for m in (metrics or list(METRICS)) if m in runs.columns]
    rows = []
    for sc, g in runs.groupby("scenario", sort=False):
        a = g[g.strategy == BASE].set_index("seed")
        b = g[g.strategy == SMART].set_index("seed")
        common = a.index.intersection(b.index)
        block = []
        for m in metrics:
            x, y = a.loc[common, m].to_numpy(float), b.loc[common, m].to_numpy(float)
            ok = ~(np.isnan(x) | np.isnan(y))
            x, y = x[ok], y[ok]
            diff = y - x
            n = len(diff)
            rec = {"scenario": sc, "metric": m, "n_pairs": n,
                   "baseline_mean": float(x.mean()) if n else float("nan"),
                   "coordinated_mean": float(y.mean()) if n else float("nan"),
                   "mean_diff": float(diff.mean()) if n else float("nan"),
                   "ci95_low": float("nan"), "ci95_high": float("nan"), "cohens_dz": float("nan"),
                   "p_ttest": float("nan"), "p_wilcoxon": float("nan"), "note": ""}
            if n < 2:
                rec["note"] = "fewer than 2 pairs: no inference"
            elif np.allclose(diff, 0):
                rec["note"] = "no difference in any pair"
            else:
                rec["ci95_low"], rec["ci95_high"] = _ci(diff)
                sd = diff.std(ddof=1)
                rec["cohens_dz"] = float(diff.mean() / sd) if sd > 0 else float("nan")
                rec["p_ttest"] = float(stats.ttest_rel(y, x).pvalue) if sd > 0 else float("nan")
                if n >= 6:
                    try:
                        rec["p_wilcoxon"] = float(stats.wilcoxon(diff).pvalue)
                    except ValueError:
                        pass
                else:
                    rec["note"] = "n<6: Wilcoxon not reported"
            block.append(rec)
        adj = _holm([r["p_ttest"] for r in block])
        for r, ap in zip(block, adj, strict=True):
            r["p_ttest_holm"] = ap
        rows.extend(block)
    return pd.DataFrame(rows)


def scenario_order(runs: pd.DataFrame) -> list[str]:
    """Scenarios ordered by mean number of valid requests (demand level)."""
    return list(runs.groupby("scenario")["valid_requests"].mean().sort_values().index)


# --------------------------------------------------------------------------- figures
def _finish(fig, caption: str, n_rep: int) -> None:
    fig.text(0.01, 0.005, f"{caption}  n = {n_rep} replications per scenario/strategy. {SYNTH_NOTE}",
             fontsize=7.5, color="#444", ha="left", va="bottom", wrap=True)
    fig.tight_layout(rect=(0, 0.045, 1, 1))


def _nrep(runs: pd.DataFrame) -> int:
    return int(runs.groupby(["scenario", "strategy"]).size().min())


def fig_occupancy(res: dict, scenarios: list[str] | None = None):
    occ, runs = res["occupancy"], res["runs"]
    scs = scenarios or scenario_order(runs)
    cols = min(3, len(scs))
    rows = math.ceil(len(scs) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 3.2 * rows), squeeze=False, sharey=True)
    for ax, sc in zip(axes.flat, scs, strict=False):
        for st in (BASE, SMART):
            g = occ[(occ.scenario == sc) & (occ.strategy == st)]
            piv = g.pivot(index="time", columns="replication", values="occupancy_ratio") * 100
            mu, sd = piv.mean(axis=1), piv.std(axis=1, ddof=1).fillna(0)
            s = STYLE[st]
            ax.plot(mu.index / 60, mu, color=s["color"], ls=s["ls"], lw=1.8, label=st)
            ax.fill_between(mu.index / 60, mu - sd, mu + sd, color=s["color"], alpha=0.15)
        ax.set_title(sc.replace("_", " "), fontsize=10)
        ax.set_xlabel("Simulated time (hours from start)")
        ax.set_ylabel("Occupied spaces (% of capacity)")
        ax.set_ylim(0, 105)
        ax.grid(alpha=0.3)
    for ax in list(axes.flat)[len(scs):]:
        ax.axis("off")
    axes.flat[0].legend(title="strategy (mean ± 1 sd)", fontsize=8)
    _finish(fig, "Occupancy over simulated time.", _nrep(runs))
    return fig


def fig_success_failed(res: dict):
    runs = res["runs"]
    scs = scenario_order(runs)
    g = runs.groupby(["scenario", "strategy"])[["success_rate", "failed_rate", "pending_rate"]].mean()
    fig, ax = plt.subplots(figsize=(max(7, 1.5 * len(scs)), 4.2))
    w = 0.38
    for j, st in enumerate((BASE, SMART)):
        x = np.arange(len(scs)) + (j - 0.5) * w
        succ = np.array([g.loc[(s, st), "success_rate"] for s in scs]) * 100
        fail = np.array([g.loc[(s, st), "failed_rate"] for s in scs]) * 100
        pend = np.array([g.loc[(s, st), "pending_rate"] for s in scs]) * 100
        ax.bar(x, succ, w, color=STYLE[st]["color"], hatch=STYLE[st]["hatch"], edgecolor="white",
               label=f"{st}: successful")
        ax.bar(x, fail, w, bottom=succ, color="#999999", edgecolor="white", hatch="xx" if j else "..",
               label=f"{st}: failed")
        ax.bar(x, pend, w, bottom=succ + fail, color="#E69F00", edgecolor="white", label=f"{st}: pending" if j else None)
    ax.set_xticks(range(len(scs)), [s.replace("_", "\n") for s in scs], fontsize=8)
    ax.set_ylabel("Valid requests (%)")
    ax.set_ylim(0, 100)
    ax.set_title("Successful vs failed parking requests (scenarios ordered by demand)")
    ax.legend(fontsize=7, ncol=2, loc="lower left")
    _finish(fig, "Left bar of each pair = baseline, right bar = coordinated; means over replications.", _nrep(runs))
    return fig


def fig_strategy_comparison(res: dict, metrics=("success_rate", "mean_wait_min", "mean_drive_m", "mean_walk_m")):
    runs = res["runs"]
    summ = summarise(runs, list(metrics))
    scs = scenario_order(runs)
    fig, axes = plt.subplots(1, len(metrics), figsize=(4.2 * len(metrics), 4), squeeze=False)
    for ax, m in zip(axes[0], metrics, strict=True):
        for j, st in enumerate((BASE, SMART)):
            d = summ[(summ.metric == m) & (summ.strategy == st)].set_index("scenario").loc[scs]
            x = np.arange(len(scs)) + (j - 0.5) * 0.18
            ax.errorbar(x, d["mean"], yerr=[d["mean"] - d["ci95_low"], d["ci95_high"] - d["mean"]],
                        color=STYLE[st]["color"], marker=STYLE[st]["marker"], ls="none", capsize=3, label=st)
        ax.set_xticks(range(len(scs)), [s.replace("_", "\n") for s in scs], fontsize=6.5)
        lab, unit, _ = METRICS[m]
        ax.set_title(lab, fontsize=10)
        ax.set_ylabel(unit)
        ax.grid(alpha=0.3, axis="y")
    axes[0][0].legend(fontsize=8)
    _finish(fig, "Mean with 95% t-interval across replications; note the y-axes do not start at zero.", _nrep(runs))
    return fig


def fig_demand_levels(res: dict):
    runs = res["runs"]
    scs = scenario_order(runs)
    demand = runs.groupby("scenario")["valid_requests"].mean().loc[scs]
    summ = summarise(runs, ["success_rate", "mean_wait_min", "utilisation"])
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    for ax, m in zip(axes, ("success_rate", "mean_wait_min", "utilisation"), strict=True):
        for st in (BASE, SMART):
            d = summ[(summ.metric == m) & (summ.strategy == st)].set_index("scenario").loc[scs]
            ax.errorbar(demand.values, d["mean"], yerr=[d["mean"] - d["ci95_low"], d["ci95_high"] - d["mean"]],
                        color=STYLE[st]["color"], marker=STYLE[st]["marker"], ls=STYLE[st]["ls"], capsize=3, label=st)
        ax.set_xlabel("Demand: mean valid requests per run")
        ax.set_ylabel(METRICS[m][1])
        ax.set_title(METRICS[m][0], fontsize=10)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    _finish(fig, "Scenarios differ in more than demand (peaks, durations, capacity), so this is not a pure dose-response curve.",
            _nrep(runs))
    return fig


def fig_carpark_utilisation(res: dict):
    runs = res["runs"]
    ucols = [c for c in runs.columns if c.startswith("util_")]
    scs = scenario_order(runs)
    g = runs.groupby(["scenario", "strategy"])[ucols].mean()
    fig, ax = plt.subplots(figsize=(max(8, 2.2 * len(scs)), 4.2))
    k = len(ucols)
    w = 0.8 / (2 * k)
    shades = plt.cm.Greys(np.linspace(0.35, 0.8, k))
    for j, st in enumerate((BASE, SMART)):
        for i, c in enumerate(ucols):
            x = np.arange(len(scs)) + (j * k + i - k + 0.5) * w
            ax.bar(x, [g.loc[(s, st), c] * 100 for s in scs], w, color=STYLE[st]["color"], alpha=0.45 + 0.18 * i,
                   hatch=STYLE[st]["hatch"], edgecolor="white", label=f"{st} - {c[5:]}")
    ax.set_xticks(range(len(scs)), [s.replace("_", "\n") for s in scs], fontsize=8)
    ax.set_ylabel("Utilisation (% of space-minutes)")
    ax.set_ylim(0, 125)
    ax.set_yticks(range(0, 101, 20))
    ax.set_title("Car-park utilisation by strategy")
    ax.legend(fontsize=6.5, ncol=2)
    del shades
    _finish(fig, "Within each scenario: baseline bars (hatched) then coordinated bars; one bar per car park.", _nrep(runs))
    return fig


def fig_run_variation(res: dict, metric: str = "success_rate"):
    runs = res["runs"]
    scs = scenario_order(runs)
    fig, ax = plt.subplots(figsize=(max(8, 1.6 * len(scs)), 4.2))
    rng = np.random.default_rng(0)
    for j, st in enumerate((BASE, SMART)):
        data = [runs[(runs.scenario == s) & (runs.strategy == st)][metric].dropna().to_numpy() for s in scs]
        pos = np.arange(len(scs)) + (j - 0.5) * 0.3
        ax.boxplot(data, positions=pos, widths=0.25, showfliers=False, patch_artist=True,
                   boxprops=dict(facecolor="white", edgecolor=STYLE[st]["color"], hatch=STYLE[st]["hatch"]),
                   medianprops=dict(color=STYLE[st]["color"]))
        for p, d in zip(pos, data, strict=True):
            ax.scatter(p + rng.uniform(-0.05, 0.05, len(d)), d, s=9, color=STYLE[st]["color"], marker=STYLE[st]["marker"],
                       alpha=0.6, label=st if p == pos[0] else None)
    ax.set_xticks(range(len(scs)), [s.replace("_", "\n") for s in scs], fontsize=8)
    ax.set_ylabel(f"{METRICS[metric][0]} ({METRICS[metric][1]})")
    ax.set_title(f"Run-to-run variation: {METRICS[metric][0]}")
    ax.grid(alpha=0.3, axis="y")
    ax.legend(fontsize=8)
    _finish(fig, "Each dot is one replication; box = IQR; whiskers exclude outliers.", _nrep(runs))
    return fig


def fig_sustainability(res: dict):
    runs = res["runs"]
    scs = scenario_order(runs)
    summ = summarise(runs, ["co2e_proxy_g_per_request", "mean_drive_m"])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, m, lab in zip(axes, ("co2e_proxy_g_per_request", "mean_drive_m"),
                          ("CO2e proxy per valid request (g, simulation estimate)", "Mean drive distance (m)"), strict=True):
        for j, st in enumerate((BASE, SMART)):
            d = summ[(summ.metric == m) & (summ.strategy == st)].set_index("scenario").loc[scs]
            x = np.arange(len(scs)) + (j - 0.5) * 0.18
            ax.errorbar(x, d["mean"], yerr=[d["mean"] - d["ci95_low"], d["ci95_high"] - d["mean"]],
                        color=STYLE[st]["color"], marker=STYLE[st]["marker"], ls="none", capsize=3, label=st)
        ax.set_xticks(range(len(scs)), [s.replace("_", "\n") for s in scs], fontsize=7)
        ax.set_ylabel(lab, fontsize=8)
        ax.grid(alpha=0.3, axis="y")
    axes[0].legend(fontsize=8)
    axes[0].set_title("Emission proxy (assumption-based)", fontsize=10)
    axes[1].set_title("Driving distance driving the proxy", fontsize=10)
    _finish(fig, "Proxy = in-park drive km x g/km + idle waiting min x g/min (illustrative factors, see docs/metrics.md); not measured impact.",
            _nrep(runs))
    return fig


FIGURES = {
    "occupancy_over_time": fig_occupancy,
    "success_vs_failed": fig_success_failed,
    "strategy_comparison": fig_strategy_comparison,
    "demand_levels": fig_demand_levels,
    "carpark_utilisation": fig_carpark_utilisation,
    "run_variation": fig_run_variation,
    "sustainability_proxy": fig_sustainability,
}


def analyse(results_dir: str | Path, make_figs: bool = True) -> dict[str, Path]:
    """Regenerate summary/comparison tables (CSV + Markdown) and figures from saved results."""
    res = load_results(results_dir)
    d = Path(results_dir)
    out: dict[str, Path] = {}
    summ = summarise(res["runs"])
    comp = compare_strategies(res["runs"])
    summ.to_csv(d / "summary_by_scenario.csv", index=False)
    comp.to_csv(d / "comparison_paired.csv", index=False)
    out["summary"], out["comparison"] = d / "summary_by_scenario.csv", d / "comparison_paired.csv"
    (d / "tables.md").write_text(_markdown_tables(summ, comp, res["meta"]), encoding="utf-8")
    out["tables_md"] = d / "tables.md"
    if make_figs:
        fd = d / "figures"
        fd.mkdir(exist_ok=True)
        for name, fn in FIGURES.items():
            fig = fn(res)
            p = fd / f"{name}.png"
            fig.savefig(p, dpi=140)
            plt.close(fig)
            out[name] = p
    return out


def _markdown_tables(summ: pd.DataFrame, comp: pd.DataFrame, meta: dict) -> str:
    lines = ["# Experiment tables (auto-generated)\n",
             f"{meta.get('data_origin', SYNTH_NOTE)}  \nMode: {meta.get('mode')}, replications: {meta.get('replications')}, "
             f"base seed: {meta.get('base_seed')}.\n",
             "## Means by scenario and strategy (95% t-interval)\n",
             "| scenario | strategy | metric | mean | 95% CI | sd | n |", "|---|---|---|---|---|---|---|"]
    for r in summ[summ.metric.isin(["success_rate", "failed_rate", "utilisation", "mean_wait_min", "mean_drive_m",
                                    "mean_walk_m", "co2e_proxy_kg"])].itertuples():
        lines.append(f"| {r.scenario} | {r.strategy} | {r.metric} | {r.mean:.4g} | [{r.ci95_low:.4g}, {r.ci95_high:.4g}] | {r.sd:.3g} | {r.n} |")
    lines += ["", "## Paired differences (coordinated - baseline)\n",
              "| scenario | metric | pairs | mean diff | 95% CI | d_z | p (t) | p (t, Holm) | p (Wilcoxon) | note |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in comp.itertuples():
        lines.append(f"| {r.scenario} | {r.metric} | {r.n_pairs} | {r.mean_diff:.4g} | [{r.ci95_low:.4g}, {r.ci95_high:.4g}] | "
                     f"{r.cohens_dz:.3g} | {r.p_ttest:.3g} | {r.p_ttest_holm:.3g} | {r.p_wilcoxon:.3g} | {r.note} |")
    lines.append("\nSee docs/experiment_methodology.md for how to read these tables.")
    return "\n".join(lines) + "\n"

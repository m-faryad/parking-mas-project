# Experiment methodology

* **Design:** for each scenario and replication r, seed = `base_seed + 1000*scenario_index + r`. The arrival stream is generated once and used by **both** strategies (paired design / common random numbers).
* **Replications:** demo mode 5 (2 scenarios), research mode 30 (7 scenarios); configurable (`--replications`).
* **Default seed:** 2026 (`--seed`). Same code + seed → identical `runs.csv` apart from wall-clock columns (tested).
* **Statistics (analytics.py):** per scenario × strategy: mean, sd, 95% t-interval. Paired comparison (coordinated − baseline): mean difference with 95% t-interval, Cohen's d_z (mean diff ÷ sd of diffs), paired t-test, Wilcoxon signed-rank (n ≥ 6), Holm adjustment of the t-test p-values across the metrics of a scenario.
* **Interpretation cautions:** replications are simulated, so p-values shrink as you add runs; look at effect size and whether the interval has practical meaning. Metrics are correlated (not independent tests). Not computed when all differences are zero or n < 2. Scenario parameters are synthetic, so conclusions apply to the model, not to real car parks.
* **Sources of non-determinism:** only wall-clock timings. Set-ordering is not used for decisions; ties are broken by car-park order then index.
* **Regenerate:** `REPRODUCE_RESULTS.bat` or `python -m parking_mas.cli experiment --mode research --overwrite`; re-analyse saved data with `python -m parking_mas.cli analyse results/research`.

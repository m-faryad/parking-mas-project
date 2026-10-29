"""Command line interface:  python -m parking_mas.cli <command>

  run         run one simulation and print its metrics
  experiment  run a replicated paired experiment and analyse it
  analyse     regenerate tables/figures from a saved results folder
  scenarios   (re)write the predefined scenario JSON files
  check       verify environment, files and configs
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from .analytics import ResultsError, analyse  # noqa: E402
from .config import ConfigError, load_config, predefined_scenarios, write_scenario_files  # noqa: E402
from .datagen import load_arrivals  # noqa: E402
from .engine import Simulation  # noqa: E402
from .experiment import run_experiment  # noqa: E402
from .metrics import compute_metrics  # noqa: E402

MODES = {"demo": dict(replications=5, scenarios=["moderate_demand", "high_demand"]),
         "research": dict(replications=30, scenarios=list(predefined_scenarios()))}


def _progress(done: int, total: int, msg: str) -> None:
    if done == total or done % max(1, total // 10) == 0:
        print(f"  [{done}/{total}] {msg}", flush=True)


def cmd_run(a) -> int:
    cfg = load_config(a.config) if a.config else predefined_scenarios()[a.scenario]
    if a.seed is not None:
        cfg.seed = a.seed
    arrivals = load_arrivals(a.arrivals) if a.arrivals else None
    m = compute_metrics(Simulation(cfg, a.strategy, arrivals).run())
    print(json.dumps(m, indent=2, default=float))
    return 0


def cmd_experiment(a) -> int:
    mode = MODES[a.mode]
    reps = a.replications or mode["replications"]
    pool = predefined_scenarios()
    names = a.scenarios or mode["scenarios"]
    unknown = [n for n in names if n not in pool]
    if unknown:
        print(f"unknown scenario(s) {unknown}; available: {list(pool)}", file=sys.stderr)
        return 2
    out = Path(a.out) if a.out else ROOT / "results" / (a.mode if a.mode != "custom" else datetime.now().strftime("run_%Y%m%d_%H%M%S"))
    if out.exists() and any(out.iterdir()) and not a.overwrite:
        print(f"Results already exist in {out}\nNot overwriting. Use --overwrite or --out <new folder>.")
        return 0 if a.skip_existing else 3
    print(f"Running {len(names)} scenario(s) x {reps} replication(s) x 2 strategies (base seed {a.seed}) ...")
    run_experiment([pool[n] for n in names], reps, a.seed, out, mode=a.mode, overwrite=a.overwrite, progress=_progress)
    files = analyse(out)
    print(f"\nResults:  {out}\nTables:   {files['tables_md']}\nFigures:  {out / 'figures'}")
    return 0


def cmd_analyse(a) -> int:
    files = analyse(a.results)
    print("Wrote:\n  " + "\n  ".join(str(p) for p in files.values()))
    return 0


def cmd_scenarios(a) -> int:
    for p in write_scenario_files(ROOT / "configs" / "scenarios"):
        print("wrote", p)
    return 0


def cmd_check(a) -> int:
    problems = 0

    def ok(c: bool, msg: str) -> None:
        nonlocal problems
        print(("[ OK ] " if c else "[FAIL] ") + msg)
        problems += 0 if c else 1

    ok(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]} (need >= 3.10)")
    print(("[ OK ] " if sys.prefix != sys.base_prefix else "[WARN] not") + " running inside a virtual environment (.venv)")
    for mod in ("numpy", "pandas", "scipy", "matplotlib", "plotly", "streamlit", "pytest"):
        try:
            m = __import__(mod)
            ok(True, f"{mod} {getattr(m, '__version__', '')}")
        except ImportError:
            ok(False, f"{mod} not installed")
    for rel in ("app/streamlit_app.py", "configs/scenarios", "data/sample/sample_arrivals.csv", "docs/README_DOCS.md"):
        ok((ROOT / rel).exists(), f"file present: {rel}")
    for p in sorted((ROOT / "configs" / "scenarios").glob("*.json")):
        try:
            load_config(p)
            ok(True, f"config valid: {p.name}")
        except ConfigError as exc:
            ok(False, f"config invalid: {p.name}: {exc}")
    print("\nEnvironment check " + ("PASSED" if not problems else f"FAILED ({problems} problem(s))"))
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="parking_mas")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--scenario", default="moderate_demand")
    r.add_argument("--config")
    r.add_argument("--arrivals")
    r.add_argument("--strategy", default="coordinated", choices=["baseline", "coordinated"])
    r.add_argument("--seed", type=int)
    r.set_defaults(fn=cmd_run)
    e = sub.add_parser("experiment")
    e.add_argument("--mode", choices=["demo", "research", "custom"], default="demo")
    e.add_argument("--scenarios", nargs="*")
    e.add_argument("--replications", type=int)
    e.add_argument("--seed", type=int, default=2026)
    e.add_argument("--out")
    e.add_argument("--overwrite", action="store_true")
    e.add_argument("--skip-existing", action="store_true")
    e.set_defaults(fn=cmd_experiment)
    an = sub.add_parser("analyse")
    an.add_argument("results")
    an.set_defaults(fn=cmd_analyse)
    sub.add_parser("scenarios").set_defaults(fn=cmd_scenarios)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except (ConfigError, ResultsError, FileExistsError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

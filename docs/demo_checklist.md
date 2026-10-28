# Demo checklist (technical aid – write your own presentation)

Before: run `CHECK_ENVIRONMENT.bat`, `RUN_TESTS.bat`; open `RUN_DEMO.bat`; have `results/demo` and `results/research` available; close other Streamlit windows.

Suggested technical sequence (20–30 min):
1. Architecture (Methodology page / architecture.md): four agents, message flow.
2. Scenarios page: load `high_demand`, change seed/capacity, show validation error (set capacity 0), export JSON.
3. Simulation page: run baseline live (Start/Pause/Resume/Step), then Reset; same scenario with coordinated.
4. Inspector: space grid, decision log with reasons, message counts.
5. Experiments: run a small paired experiment; read the difference table and interval.
6. Analytics: open `results/research`; show occupancy, success vs failed, strategy comparison, run variation, emission proxy (and its caveats).
7. Tests: show `RUN_TESTS.bat` output; mention invariants and reproducibility test.
8. Limitations and future work (known_limitations.md).

Likely failures: port busy; Python not on PATH; empty analytics (no results yet); live run slow (raise speed).

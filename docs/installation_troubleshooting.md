# Installation and troubleshooting (Windows)

Prerequisite: Python 3.10+ from python.org (tick "Add python.exe to PATH") or the `py` launcher.
1. `INSTALL.bat` – creates `.venv`, installs `requirements.txt`, verifies imports.
2. `CHECK_ENVIRONMENT.bat` – reports Python, venv, packages, files, configs.
3. `RUN.bat` – starts the dashboard at http://localhost:8501.
4. `RUN_TESTS.bat` – full test suite (exit code 0 = pass).
5. `REPRODUCE_RESULTS.bat` – demo-size or full experiments (asks before overwriting).
6. `RUN_DEMO.bat` – demo configuration with fixed seed 2026, then opens the dashboard.

| Problem | Fix |
|---|---|
| "Python was not found" | Install Python 3.10+, tick PATH, reopen the window |
| pip cannot download | Check network/proxy; rerun INSTALL.bat |
| Port 8501 busy | Close the other Streamlit window or edit `--server.port` in RUN.bat |
| Browser doesn't open | Open the printed URL manually |
| `ModuleNotFoundError` | Run INSTALL.bat again |
| Antivirus/PowerShell policy | The scripts are plain .bat; do not need admin rights |
| Results exist | REPRODUCE_RESULTS.bat asks; choose a new folder or overwrite |
| Analytics page empty | Run REPRODUCE_RESULTS.bat or the Experiments page |

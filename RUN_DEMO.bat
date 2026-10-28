@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run INSTALL.bat first.
  if "%NOPAUSE%"=="" pause
  exit /b 1
)
set "PYTHONPATH=%~dp0src"
set "PARKING_MAS_DEMO=1"
if exist "results\demo\runs.csv" (
  echo Existing demo results found in results\demo - keeping them, not overwritten.
) else (
  echo Generating demo results: seed 2026, 5 replications, 2 scenarios ...
  ".venv\Scripts\python.exe" -m parking_mas.cli experiment --mode demo --seed 2026
  if errorlevel 1 (
    echo [ERROR] Demo experiment failed.
    if "%NOPAUSE%"=="" pause
    exit /b 1
  )
)
echo.
echo Launching the dashboard with demo configuration configs\demo_config.json (high demand, seed 2026).
echo URL: http://localhost:8501
".venv\Scripts\python.exe" -m streamlit run "app\streamlit_app.py" --server.port 8501
if "%NOPAUSE%"=="" pause
exit /b %errorlevel%

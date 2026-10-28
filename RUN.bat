@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run INSTALL.bat first.
  if "%NOPAUSE%"=="" pause
  exit /b 1
)
set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -c "import streamlit, pandas, plotly, matplotlib, scipy" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Required packages are missing. Run INSTALL.bat again.
  if "%NOPAUSE%"=="" pause
  exit /b 1
)
echo Starting the dashboard. Open  http://localhost:8501  if the browser does not open.
echo Press Ctrl+C in this window to stop.
".venv\Scripts\python.exe" -m streamlit run "app\streamlit_app.py" --server.port 8501
if errorlevel 1 (
  echo [ERROR] The application stopped with an error. Is port 8501 already in use?
)
if "%NOPAUSE%"=="" pause
exit /b %errorlevel%

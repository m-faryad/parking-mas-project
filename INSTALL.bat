@echo off
setlocal
cd /d "%~dp0"
echo ==== Parking MAS: install ====
set "PYCMD="
where py >nul 2>nul
if not errorlevel 1 set "PYCMD=py -3"
if not defined PYCMD (
  where python >nul 2>nul
  if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
  echo [ERROR] Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/
  echo         and tick "Add python.exe to PATH", then run INSTALL.bat again.
  goto :fail
)
%PYCMD% -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.10 or newer is required. Found:
  %PYCMD% --version
  goto :fail
)
echo Using:
%PYCMD% --version
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment in .venv ...
  %PYCMD% -m venv ".venv"
  if errorlevel 1 (
    echo [ERROR] Could not create the virtual environment.
    goto :fail
  )
) else (
  echo Re-using existing .venv
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 echo [WARN] pip upgrade failed; continuing.
echo Installing dependencies (this can take a few minutes) ...
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 (
  echo [ERROR] Dependency installation failed. Check your internet connection or proxy and run again.
  goto :fail
)
set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -c "import numpy, pandas, scipy, matplotlib, plotly, streamlit, parking_mas; print('Import check passed, parking_mas', parking_mas.__version__)"
if errorlevel 1 (
  echo [ERROR] Installation verification failed.
  goto :fail
)
echo.
echo SUCCESS. Next: RUN_TESTS.bat, then RUN.bat
if "%NOPAUSE%"=="" pause
exit /b 0
:fail
echo.
echo INSTALL FAILED. See docs\installation_troubleshooting.md
if "%NOPAUSE%"=="" pause
exit /b 1

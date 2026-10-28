@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "PYEXE="
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"
if not defined PYEXE (
  where python >nul 2>nul
  if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE (
  where py >nul 2>nul
  if not errorlevel 1 set "PYEXE=py -3"
)
if not defined PYEXE (
  echo [FAIL] Python not found. Install Python 3.10+ from https://www.python.org/downloads/
  if "%NOPAUSE%"=="" pause
  exit /b 1
)
%PYEXE% -m parking_mas.cli check
set "RC=%errorlevel%"
if "%NOPAUSE%"=="" pause
exit /b %RC%

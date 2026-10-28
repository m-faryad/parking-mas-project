@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run INSTALL.bat first.
  if "%NOPAUSE%"=="" pause
  exit /b 1
)
set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -m pytest -q
set "RC=%errorlevel%"
echo.
if "%RC%"=="0" (echo RESULT: ALL TESTS PASSED) else (echo RESULT: TESTS FAILED, exit code %RC%)
if "%NOPAUSE%"=="" pause
exit /b %RC%

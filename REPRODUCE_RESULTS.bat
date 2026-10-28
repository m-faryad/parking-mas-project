@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run INSTALL.bat first.
  if "%NOPAUSE%"=="" pause
  exit /b 1
)
set "PYTHONPATH=%~dp0src"
echo Which experiment?
echo   1 = demo     (2 scenarios x 5 replications, about 10 seconds)
echo   2 = research (7 scenarios x 30 replications, about 1-3 minutes)
set "MODE="
set /p CHOICE="Enter 1 or 2: "
if "%CHOICE%"=="1" set "MODE=demo"
if "%CHOICE%"=="2" set "MODE=research"
if not defined MODE (
  echo Invalid choice.
  if "%NOPAUSE%"=="" pause
  exit /b 1
)
set "OVER="
if exist "results\%MODE%\runs.csv" (
  echo Results already exist in results\%MODE%.
  set /p ANS="Overwrite them? (y/N): "
  if /i "%ANS%"=="y" (set "OVER=--overwrite") else (
    echo Keeping existing results. Re-analysing them only ...
    ".venv\Scripts\python.exe" -m parking_mas.cli analyse "results\%MODE%"
    goto :done
  )
)
".venv\Scripts\python.exe" -m parking_mas.cli experiment --mode %MODE% --seed 2026 %OVER%
:done
set "RC=%errorlevel%"
echo.
echo Output folder: %~dp0results\%MODE%   (tables.md, runs.csv, figures\)
if "%NOPAUSE%"=="" pause
exit /b %RC%

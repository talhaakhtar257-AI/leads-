@echo off
rem LeadScout launcher for Windows: double-click this file.
rem First run: creates a private Python environment and installs LeadScout.
rem Every run: opens the dashboard in your browser.
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && (py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3")
if not defined PY (
  where python >nul 2>nul && (python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python")
)
if not defined PY (
  echo LeadScout needs Python 3.10 or newer.
  echo Download it from https://www.python.org/downloads/ and tick "Add python.exe to PATH" when installing.
  echo Then double-click this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\leadscout.exe" (
  echo First run: setting up LeadScout ^(this takes a minute^)...
  %PY% -m venv .venv || goto :failed
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -e ".[web,packs]" || goto :failed
)

if not exist "campaign.yaml" ".venv\Scripts\leadscout.exe" init

echo Starting LeadScout. Keep this window open while you use it; close it to stop.
".venv\Scripts\leadscout.exe" web --open
if errorlevel 1 (
  echo LeadScout stopped with an error ^(see above^).
  pause
)
exit /b 0

:failed
echo Installing LeadScout failed. Check your internet connection and try again.
if exist ".venv" rmdir /s /q ".venv"
pause
exit /b 1

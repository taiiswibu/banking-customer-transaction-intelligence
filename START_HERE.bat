@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 scripts\build.py > build.log 2>&1
) else (
  python scripts\build.py > build.log 2>&1
)
if errorlevel 1 (
  type build.log
  echo.
  echo Build failed. See build.log. Python 3.10 or newer is required.
  pause
  exit /b 1
)
type build.log
echo.
echo Opening Power BI project. Choose Refresh to import CSV data.
start "" "%~dp0powerbi\Banking.pbip"
pause

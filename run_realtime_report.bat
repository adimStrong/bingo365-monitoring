@echo off
REM ============================================================
REM Real-Time KPI Report Scheduler for Windows
REM BINGO365 Monitoring Dashboard
REM ============================================================

REM Set working directory to script location
cd /d "%~dp0"

REM Set Python path (adjust if needed)
SET PYTHON_PATH=python

REM Log file for output
SET LOG_FILE=realtime_scheduler.log

echo ============================================================
echo Real-Time KPI Report Scheduler
echo Started: %date% %time%
echo ============================================================

REM Check if Python is available
%PYTHON_PATH% --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python or update PYTHON_PATH.
    pause
    exit /b 1
)

REM Install dependencies if needed
echo Checking dependencies...
%PYTHON_PATH% -c "import apscheduler" >nul 2>&1
if errorlevel 1 (
    echo Installing APScheduler...
    %PYTHON_PATH% -m pip install apscheduler
)

%PYTHON_PATH% -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo Installing Playwright...
    %PYTHON_PATH% -m pip install playwright
    %PYTHON_PATH% -m playwright install chromium
)

REM Parse command line arguments
if "%1"=="--run-now" (
    echo Running immediate report...
    %PYTHON_PATH% send_realtime_report.py --run-now
    goto :end
)

if "%1"=="--text-only" (
    echo Running text-only report...
    %PYTHON_PATH% send_realtime_report.py --run-now --text-only
    goto :end
)

if "%1"=="--show-schedule" (
    %PYTHON_PATH% send_realtime_report.py --show-schedule
    goto :end
)

REM Start the scheduler daemon
echo Starting scheduler daemon...
echo Log file: %LOG_FILE%
echo Press Ctrl+C to stop
echo.

%PYTHON_PATH% send_realtime_report.py --daemon >> %LOG_FILE% 2>&1

:end
echo.
echo ============================================================
echo Finished: %date% %time%
echo ============================================================

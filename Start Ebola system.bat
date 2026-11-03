@echo off
title Ebola outbreak analytics - live system
call "%~dp0_env.bat" || exit /b 1

rem 1. Make sure the watcher runs automatically every 3 hours
schtasks /query /tn "Ebola outbreak watcher" >nul 2>&1
if errorlevel 1 (
    schtasks /create /tn "Ebola outbreak watcher" /tr "\"%~dp0run_watch_once.bat\"" /sc hourly /mo 3 /f >nul
    echo Automatic updates switched on: the official sources are checked every 3 hours.
) else (
    echo Automatic updates are on: the official sources are checked every 3 hours.
)

rem 2. Check the sources now, in the background
start "Ebola watcher" /min cmd /c "%~dp0run_watch_once.bat"

rem 3. Open the live dashboard
echo Opening the dashboard in your browser. Keep this window open while you use it.
streamlit run dashboard.py --server.port 8501

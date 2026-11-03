@echo off
rem One pass of the watcher. Run by Windows Task Scheduler every 3 hours.
call "%~dp0_env.bat" || exit /b 1
python watch.py >> "data\watch_console.txt" 2>&1

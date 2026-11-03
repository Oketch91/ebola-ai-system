@echo off
title Ebola outbreak analytics - retrospective replay
call "%~dp0_env.bat" || exit /b 1
if not exist "results\replay_history.csv" (
    echo Building the replay from the reports folder. This takes about 5 minutes, once.
    python replay_history.py
)
echo Opening the replay in your browser. Keep this window open while you use it.
streamlit run dashboard.py --server.port 8502 -- --replay

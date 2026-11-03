@echo off
rem Use after changing the files in the reports folder.
call "%~dp0_env.bat" || exit /b 1
echo Rebuilding the replay from the reports folder (about 5 minutes)...
python replay_history.py
echo Done. Close and reopen "Start replay (colloquium).bat" to see the new replay.
pause

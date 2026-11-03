@echo off
schtasks /delete /tn "Ebola outbreak watcher" /f
echo Automatic updates switched off. Double-click "Start Ebola system.bat" to switch them on again.
pause

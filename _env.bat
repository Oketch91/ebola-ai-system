@echo off
rem Finds Anaconda and activates it. Used by the other launchers.
set "CONDA=%USERPROFILE%\AppData\Local\anaconda3"
if not exist "%CONDA%\Scripts\activate.bat" set "CONDA=%USERPROFILE%\anaconda3"
if not exist "%CONDA%\Scripts\activate.bat" set "CONDA=C:\ProgramData\anaconda3"
if not exist "%CONDA%\Scripts\activate.bat" (
    echo Anaconda was not found. Edit _env.bat and set CONDA to your Anaconda folder.
    pause
    exit /b 1
)
call "%CONDA%\Scripts\activate.bat" "%CONDA%"
cd /d "%~dp0"
set MPLBACKEND=Agg
exit /b 0

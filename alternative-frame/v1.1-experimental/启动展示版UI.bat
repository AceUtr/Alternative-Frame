@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Zhilianqunce Presentation UI

where py >nul 2>nul
if not errorlevel 1 goto run_py
where python >nul 2>nul
if not errorlevel 1 goto run_python

echo Python 3 was not found. Install Python 3 with tkinter and add it to PATH.
pause
goto end

:run_py
py -3 ui_presentation.py
goto check_result

:run_python
python ui_presentation.py

:check_result
if errorlevel 1 (
    echo.
    echo Presentation UI failed to start. Check that Python 3 includes tkinter.
    pause
)

:end
endlocal

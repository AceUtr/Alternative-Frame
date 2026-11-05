@echo off
setlocal
cd /d "%~dp0"
title Alternative-Frame 长程任务 UI
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 ui.py
) else (
    if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
        "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" ui.py
    ) else (
        python ui.py
    )
)
if errorlevel 1 (
    echo.
    echo UI 未能启动。请确认本机已安装 Python 3，并在安装时启用了 tkinter。
    pause
)
endlocal

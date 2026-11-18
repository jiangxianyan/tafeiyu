@echo off
chcp 936 >nul
cd /d "%~dp0"
if exist "%~dp0.pause_watchdog" del "%~dp0.pause_watchdog" >nul 2>&1
start "" "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" "%~dp0.bot_runtime\tafei_watchdog.py"
call "%~dp0»úÆ÷ÈËÆô¶¯.bat"

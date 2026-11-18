@echo off
chcp 936 >nul
title 塔菲 关闭
cd /d "%~dp0"
set ASTRBOT_ROOT=C:\tafei\astrbot
type nul > "%~dp0.pause_watchdog"
py -3 "%~dp0.bot_runtime\bot_manager.py" stop
echo.
echo 已关闭。守护进程已暂停，下次点「启动塔菲」会自动恢复。
echo 按任意键退出...
pause >nul

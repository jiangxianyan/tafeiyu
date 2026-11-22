@echo off
chcp 65001 >nul
title 塔菲 关闭
cd /d "%~dp0"
set "ASTRBOT_ROOT=%~dp0astrbot"
type nul > "%~dp0.pause_watchdog"
py -3 "%~dp0.bot_runtime\bot_manager.py" stop
echo.
echo 已关闭。守护进程已暂停，下次点「启动塔菲」会自动恢复。
echo 按任意键退出...
pause >nul

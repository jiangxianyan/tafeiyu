@echo off
chcp 65001 >nul
title qqaibot 关闭机器人
cd /d "%~dp0"
set "ASTRBOT_ROOT=%~dp0astrbot"
py -3 "%~dp0.bot_runtime\bot_manager.py" stop
echo.
echo 已执行关闭，按任意键退出...
pause >nul

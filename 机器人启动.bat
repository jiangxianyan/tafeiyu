@echo off
chcp 936 >nul
setlocal
title qqaibot 机器人启动
cd /d "%~dp0"
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\python\versions\*") do if not defined PY if exist "%%D\python.exe" set "PY=%%D\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY (
  echo [错误] 没找到可用的 Python（可能只装了 Microsoft Store 的占位别名）。
  echo 解决：到 python.org 下载 Python 3.12+ 安装，安装首页务必勾选 "Add python.exe to PATH"，
  echo 装完后关掉本窗口重新双击即可。
  pause
  exit /b 1
)
echo [启动] 使用解释器: %PY%
%PY% "%~dp0.bot_runtime\bot_manager.py" start
echo.
:menu
echo.
echo   ========= QQ AI 机器人控制台 =========
echo     [1] 再次启动（清理残留后重启）
echo     [2] 停止机器人
echo     [3] 查看运行状态
echo     [0] 退出（不影响机器人运行）
echo   --------------------------------------
echo   关机器人: 按 [2]；或关 qqaibot-AstrBot / qqaibot-NapCat 两个窗口
echo   （本控制台窗口随时可关，不影响机器人）
echo   ======================================
set "choice="
set /p choice=请输入数字后回车: 
if "%choice%"=="1" %PY% "%~dp0.bot_runtime\bot_manager.py" start
if "%choice%"=="2" %PY% "%~dp0.bot_runtime\bot_manager.py" stop
if "%choice%"=="3" %PY% "%~dp0.bot_runtime\bot_manager.py" status
if "%choice%"=="0" exit
goto menu

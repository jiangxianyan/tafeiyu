@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PY312=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
set "PYW312=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if exist "%PYW312%" (
  "%PY312%" "%~dp0launcher\runtime_repair.py" >nul 2>&1
  start "" "%PYW312%" "%~dp0launcher\start_tafei.pyw"
  exit /b 0
)
where py >nul 2>&1
if errorlevel 1 goto missing_python
py -3.12 -c "import sys" >nul 2>&1
if errorlevel 1 goto missing_python
py -3.12 "%~dp0launcher\runtime_repair.py" >nul 2>&1
start "" pyw -3.12 "%~dp0launcher\start_tafei.pyw"
exit /b 0
:missing_python
echo Python 3.12 was not found.
echo Install Python 3.12, then run this file again:
echo https://www.python.org/downloads/windows/
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

@echo off
setlocal
cd /d "%~dp0"
set "PYW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not exist "%PYW%" set "PYW=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
if exist "%PYW%" (
  start "" "%PYW%" "%~dp0launcher\start_tafei.pyw"
  exit /b 0
)
where pyw >nul 2>&1
if not errorlevel 1 (
  start "" pyw -3 "%~dp0launcher\start_tafei.pyw"
  exit /b 0
)
where pythonw >nul 2>&1
if not errorlevel 1 (
  start "" pythonw "%~dp0launcher\start_tafei.pyw"
  exit /b 0
)
echo Python 3 is required to start Taffy.
pause
exit /b 1

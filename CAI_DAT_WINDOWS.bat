@echo off
cd /d "%~dp0"
where node >nul 2>&1
if errorlevel 1 goto missing
node -e "if(Number(process.versions.node.split('.')[0])<20)process.exit(1)"
if errorlevel 1 goto missing
where py >nul 2>&1
if errorlevel 1 (python -m venv python_v79\.venv) else (py -3 -m venv python_v79\.venv)
if errorlevel 1 goto failed
python_v79\.venv\Scripts\python.exe -c "import sys; assert sys.version_info >= (3,9)"
if errorlevel 1 goto failed
call npm ci --ignore-scripts --no-audit --no-fund
if errorlevel 1 goto failed
python_v79\.venv\Scripts\python.exe -m pip install websockets==15.0.1
if errorlevel 1 goto failed
call npx playwright install chromium
if errorlevel 1 goto failed
node scripts/set-windows-defaults.js
if errorlevel 1 goto failed
echo Cai xong. Mo CHAY_WINDOWS.bat.
pause
exit /b 0
:missing
echo Can cai Node.js 20+ va Python 3.9+ truoc.
pause
exit /b 1
:failed
echo Cai dat chua hoan tat. Kiem tra loi o tren va ket noi Internet.
pause
exit /b 1

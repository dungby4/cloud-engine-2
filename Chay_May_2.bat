@echo off
title D-AUTO v7.9 [MAY 2 - TIEN TO htdvipb]
cd /d "%~dp0"

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8088 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

start "D-AUTO AUTO-SYNC 24/7" /min cmd /c "python auto_sync_watcher.py || py auto_sync_watcher.py"

python -u chay_web_auto.py --machine 2 --prefix htdvipb %* || py -u chay_web_auto.py --machine 2 --prefix htdvipb %*
pause

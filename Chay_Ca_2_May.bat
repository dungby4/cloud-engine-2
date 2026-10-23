@echo off
title D-AUTO v7.9 [CHAY CA 2 MAY - MAY 1 + MAY 2]
cd /d "%~dp0"

echo ======================================================================
echo    KHOI DONG DONG THOI CA MAY 1 (htdvipa) VA MAY 2 (htdvipb)
echo ======================================================================

start "D-AUTO AUTO-SYNC 24/7" /min cmd /c "python auto_sync_watcher.py || py auto_sync_watcher.py"

start "D-AUTO [MAY 2 - TIEN TO htdvipb]" cmd /k "python -u chay_web_auto.py --machine 2 --prefix htdvipb --port 8089"

python -u chay_web_auto.py --machine 1 --prefix htdvipa --port 8088 %* || py -u chay_web_auto.py --machine 1 --prefix htdvipa --port 8088 %*
pause

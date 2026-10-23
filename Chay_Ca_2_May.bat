@echo off
title D-AUTO v7.9 [CHAY CA 2 MAY - MAY 1 + MAY 2]
cd /d "%~dp0"

echo ======================================================================
echo    KHOI DONG DONG THOI CA MAY 1 (htd_vip) VA MAY 2 (htd_m2)
echo ======================================================================

start "D-AUTO AUTO-SYNC 24/7" /min cmd /c "python auto_sync_watcher.py || py auto_sync_watcher.py"

start "D-AUTO [MAY 2 - TIEN TO htd_m2]" cmd /k "python chay_web_auto.py --machine 2 --prefix htd_m2 --port 8089"

python chay_web_auto.py --machine 1 --prefix htd_vip --port 8088 %* || py chay_web_auto.py --machine 1 --prefix htd_vip --port 8088 %*
pause

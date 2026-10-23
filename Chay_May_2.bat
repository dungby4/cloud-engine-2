@echo off
title D-AUTO v7.9 [MAY 2 - TIEN TO htd_m2]
cd /d "%~dp0"

start "D-AUTO AUTO-SYNC 24/7" /min cmd /c "python auto_sync_watcher.py || py auto_sync_watcher.py"

python chay_web_auto.py --machine 2 --prefix htd_m2 %* || py chay_web_auto.py --machine 2 --prefix htd_m2 %*
pause

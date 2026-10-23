@echo off
title D-AUTO v7.9 [MAY 1 - TIEN TO htd_vip]
cd /d "%~dp0"

start "D-AUTO AUTO-SYNC 24/7" /min cmd /c "python auto_sync_watcher.py || py auto_sync_watcher.py"

python chay_web_auto.py --machine 1 --prefix htd_vip %* || py chay_web_auto.py --machine 1 --prefix htd_vip %*
pause

@echo off
chcp 65001 >nul
title D-AUTO v7.9 [MÁY 2 - TIỀN TỐ htd_m2]
cd /d "%~dp0"

:: 1. Tự động bật tiến trình Auto-Sync Watcher 24/7 ngầm (bơm nick + ảnh vào Bot)
start "D-AUTO AUTO-SYNC 24/7" /min cmd /c "python auto_sync_watcher.py || py auto_sync_watcher.py"

:: 2. Khởi chạy Tool Auto Reroll Máy 2
python chay_web_auto.py --machine 2 --prefix htd_m2 %* || py chay_web_auto.py --machine 2 --prefix htd_m2 %*
pause

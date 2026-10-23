@echo off
chcp 65001 >nul
title D-AUTO v7.9 [CHẠY CẢ 2 TIẾN TRÌNH - MÁY 1 + MÁY 2]
cd /d "%~dp0"

echo ======================================================================
echo    KHỞI ĐỘNG ĐỒNG THỜI CẢ MÁY 1 (htd_vip) VÀ MÁY 2 (htd_m2)
echo ======================================================================

:: 1. Bật tiến trình Auto-Sync Watcher 24/7 ngầm
start "D-AUTO AUTO-SYNC 24/7" /min cmd /c "python auto_sync_watcher.py || py auto_sync_watcher.py"

:: 2. Khởi chạy Máy 2 ở cửa sổ riêng (port 8089)
start "D-AUTO [MÁY 2 - TIỀN TỐ htd_m2]" cmd /k "python chay_web_auto.py --machine 2 --prefix htd_m2 --port 8089"

:: 3. Khởi chạy Máy 1 ở cửa sổ này (port 8088)
python chay_web_auto.py --machine 1 --prefix htd_vip --port 8088 %* || py chay_web_auto.py --machine 1 --prefix htd_vip --port 8088 %*
pause

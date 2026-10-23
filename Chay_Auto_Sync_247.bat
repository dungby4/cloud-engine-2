@echo off
chcp 65001 >nul
echo ======================================================================
echo    TỰ ĐỘNG BƠM NICK HẮC TÂY DU 24/7 VÀO BOT TELEGRAM (AUTO-SYNC)
echo ======================================================================
echo Script này sẽ chạy ngầm theo dõi DAN_NICK_TRUNG_TUONG.txt.
echo Cứ khi nào máy treo tool có nick mới -> Tự động nạp vào Bot ngay!
echo ======================================================================
python "%~dp0auto_sync_watcher.py"
pause

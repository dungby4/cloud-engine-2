@echo off
chcp 65001 >nul
cd /d "%~dp0"
title D-AUTO - AUTO-SYNC BOT 24/7
echo ======================================================================
echo    TU DONG BOM NICK HAC TAY DU 24/7 VAO BOT TELEGRAM (AUTO-SYNC)
echo ======================================================================
echo Script nay theo doi file DAN_NICK_TRUNG_TUONG.txt.
echo Cu khi nao co nick moi, script se tu dong ban Webhook sang Bot!
echo ======================================================================
python "%~dp0auto_sync_watcher.py" || py "%~dp0auto_sync_watcher.py"
pause

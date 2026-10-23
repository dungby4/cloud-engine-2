@echo off
chcp 65001 >nul
title D-AUTO v7.9 - LIVE CMD SAN 2x DUONG TIEN / 2x NGO KHONG (LUU SA HA S6)
cd /d "%~dp0"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8088 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
python chay_web_auto.py %* || py chay_web_auto.py %* || python3 chay_web_auto.py %*
pause

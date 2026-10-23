@echo off
chcp 65001 >nul
title D-AUTO v7.9 [MÁY 1 - TIỀN TỐ htd_vip]
cd /d "%~dp0"
python chay_web_auto.py --machine 1 --prefix htd_vip %* || py chay_web_auto.py --machine 1 --prefix htd_vip %*
pause

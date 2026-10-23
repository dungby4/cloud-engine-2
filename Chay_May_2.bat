@echo off
chcp 65001 >nul
title D-AUTO v7.9 [MÁY 2 - TIỀN TỐ htd_m2]
cd /d "%~dp0"
python chay_web_auto.py --machine 2 --prefix htd_m2 %* || py chay_web_auto.py --machine 2 --prefix htd_m2 %*
pause

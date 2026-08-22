@echo off
title Apollo Quant Trading - Live Scanner & Kronos AI
cd /d "%~dp0"
echo ===================================================
echo   APOLLO QUANT TRADING - LIVE SCANNER
echo ===================================================
echo Starting 5-minute automated market scan with Kronos AI...
"..\kronos-stock-forecast\.venv\Scripts\python.exe" main_complete.py --mode scan --alerts console
pause

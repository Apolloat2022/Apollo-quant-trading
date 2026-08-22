@echo off
title Apollo Quant Trading - Dashboard & Kronos AI
cd /d "%~dp0"
echo ===================================================
echo   APOLLO QUANT TRADING PLATFORM + KRONOS AI
echo ===================================================
echo Starting Flask Web Dashboard on http://localhost:5000 ...
"..\kronos-stock-forecast\.venv\Scripts\python.exe" main_complete.py --mode dashboard
pause

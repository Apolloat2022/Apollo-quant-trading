@echo off
set "PYTHON=C:\Users\pande\AppData\Local\Programs\Python\Python311\python.exe"
start "Scanner" %SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoExit -Command "cd 'C:\DEV\APPS\quant-trading-platform'; & 'C:\Users\pande\AppData\Local\Programs\Python\Python311\python.exe' main_complete.py --mode scan --capital 10000 --alerts console"
start "Dashboard" %SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoExit -Command "cd 'C:\DEV\APPS\quant-trading-platform'; & 'C:\Users\pande\AppData\Local\Programs\Python\Python311\python.exe' main_complete.py --mode dashboard"
ping -n 6 127.0.0.1 > nul
start "" "http://localhost:5000"
exit

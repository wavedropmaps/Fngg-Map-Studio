@echo off
cd /d "%~dp0"
echo Starting FNGG Local Map Tool...
start "" http://127.0.0.1:8765
python localmaptool\server.py
pause

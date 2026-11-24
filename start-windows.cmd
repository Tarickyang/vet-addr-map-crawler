@echo off
rem Assumes installation at ~/vet-workbook inside the default WSL distribution.
start "Vet Workbook" http://localhost:8765
wsl.exe --cd ~ bash -c "bash ~/vet-workbook/run.sh"
pause

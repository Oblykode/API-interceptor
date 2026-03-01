@echo off
REM Cleanup script to kill any running instances before starting

echo Cleaning up old processes...

REM Kill Python processes
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM mitmdump.exe >nul 2>&1

REM Wait a moment for ports to be released
timeout /t 2 /nobreak >nul

echo Starting API Interceptor...
python main.py all

pause

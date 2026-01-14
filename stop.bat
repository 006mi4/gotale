@echo off
REM Hytale Server Manager - Stop Script

echo.
echo ========================================
echo Hytale Server Manager - Stopping...
echo ========================================
echo.

REM Kill Python processes (Flask app)
echo Stopping web interface...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *app.py*" >nul 2>&1

REM Kill Java processes (Hytale servers)
echo Stopping all Hytale servers...
taskkill /F /IM java.exe /FI "WINDOWTITLE eq *HytaleServer*" >nul 2>&1

echo.
echo All processes stopped.
echo.
pause

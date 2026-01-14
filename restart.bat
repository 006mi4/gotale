@echo off
REM Hytale Server Manager - Restart Script

echo.
echo ========================================
echo Hytale Server Manager - Restarting...
echo ========================================
echo.

REM Stop everything
call stop.bat

REM Wait a moment
echo Waiting 3 seconds...
timeout /t 3 /nobreak >nul

REM Start again
call start.bat

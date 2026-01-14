@echo off
REM Hytale Server Manager - Start Script

echo.
echo ========================================
echo Hytale Server Manager - Starting...
echo ========================================
echo.

REM Check if system is installed
if not exist "system\" (
    echo ERROR: System is not installed!
    echo Please run install.bat first.
    echo.
    pause
    exit /b 1
)

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed!
    echo Please run install.bat again.
    echo.
    pause
    exit /b 1
)

REM Start Flask application
echo Starting web interface...
echo Access the dashboard at: http://localhost:5000
echo.
echo Press CTRL+C to stop the server
echo.

cd system
python app.py

REM If we get here, the application has stopped
echo.
echo Application stopped.
pause

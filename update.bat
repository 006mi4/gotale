@echo off
REM Hytale Server Manager - Update Script

echo.
echo ========================================
echo Hytale Server Manager - Update
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

REM Check for running processes
tasklist /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq *app.py*" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo System is currently running. Stopping...
    call stop.bat
    echo.
)

REM Navigate to system directory
cd system

REM Check for updates
echo Checking for updates...
git fetch origin

REM Check if updates available
git rev-list HEAD...origin/main --count > temp_count.txt
set /p update_count=<temp_count.txt
del temp_count.txt

if "%update_count%"=="0" (
    echo.
    echo No updates available. System is up to date!
    echo.
    cd ..
    pause
    exit /b 0
)

echo.
echo %update_count% update(s) available.
echo.
set /p do_update="Do you want to update now? (Y/N): "

if /i not "%do_update%"=="Y" (
    echo.
    echo Update cancelled.
    cd ..
    pause
    exit /b 0
)

REM Create backup
echo.
echo Creating backup...
set backup_name=system_backup_%date:~-4,4%%date:~-7,2%%date:~-10,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set backup_name=%backup_name: =0%
cd ..
xcopy /E /I /Y system ..\%backup_name% >nul
echo Backup created: %backup_name%
echo.

REM Pull updates
echo Downloading updates...
cd system
git pull origin main

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to pull updates!
    echo Your backup is located at: %backup_name%
    echo.
    cd ..
    pause
    exit /b 1
)

REM Update Python dependencies
echo.
echo Updating Python dependencies...
python -m pip install -r requirements.txt --upgrade

echo.
echo ========================================
echo Update completed successfully!
echo ========================================
echo.

REM Show changelog if exists
if exist "CHANGELOG.md" (
    echo Recent changes:
    echo.
    type CHANGELOG.md | more
    echo.
)

cd ..

REM Ask to restart
set /p do_restart="Do you want to restart the system now? (Y/N): "
if /i "%do_restart%"=="Y" (
    echo.
    call start.bat
) else (
    echo.
    echo Update complete. Run start.bat to start the system.
    echo.
    pause
)

@echo off
title Katana Web Interface
color 0A

echo ============================================================
echo   Katana - Game Automator Web Interface
echo   Version 1.0.0
echo ============================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.7+ and try again
    echo.
    pause
    exit /b 1
)

REM Check if templates directory exists
if not exist "templates" (
    echo Creating templates directory...
    mkdir templates
    echo Please make sure index.html is in the templates\ directory
    echo.
)

REM Check if the HTML template exists
if not exist "templates\index.html" (
    echo ERROR: templates\index.html not found!
    echo Please make sure the HTML template is saved as templates\index.html
    echo.
    pause
    exit /b 1
)

echo Starting Katana Web Interface...
echo.
echo The web interface will open automatically in your browser.
echo If it doesn't open, manually navigate to: http://localhost:5000
echo.
echo Press Ctrl+C to stop the server
echo ============================================================
echo.

REM Run the startup script
python start_web.py

echo.
echo Web interface stopped.
pause
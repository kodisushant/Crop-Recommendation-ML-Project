@echo off
setlocal
title Crop Advisor - Local Server

cd /d "%~dp0.."

echo.
echo ========================================
echo          CROP ADVISOR
echo ========================================
echo.

REM Check whether Python is installed
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python 3 was not found.
        echo Install Python 3 from https://www.python.org/downloads/
        echo Make sure "Add Python to PATH" is selected.
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

REM Create virtual environment if it does not exist
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create the virtual environment.
        pause
        exit /b 1
    )
)

echo.
echo Installing/checking required packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Could not upgrade pip.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Package installation failed.
    echo Check your internet connection and Python version.
    pause
    exit /b 1
)

REM Create .env from example if it does not exist (optional)
if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul

echo.
echo Starting Crop Advisor...
echo Website: http://127.0.0.1:8000
echo API docs: http://127.0.0.1:8000/docs
echo.
echo Keep this window open while using the application.
echo Press CTRL+C to stop the server.
echo.

start "" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000"

".venv\Scripts\python.exe" -m uvicorn src.crop_advisor.main:app --host 127.0.0.1 --port 8000

echo.
echo Crop Advisor has stopped.
pause

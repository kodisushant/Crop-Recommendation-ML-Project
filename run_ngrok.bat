@echo off
setlocal
title Crop Advisor - ngrok Public Tunnel
cd /d "%~dp0"

echo.
echo ========================================
echo       CROP ADVISOR - PUBLIC TUNNEL
echo ========================================
echo.

if not exist "ngrok.exe" (
    echo ERROR: ngrok.exe was not found in this folder.
    pause
    exit /b 1
)

echo Starting ngrok tunnel to port 8000...
echo Keep this window open while sharing your public URL!
echo.

ngrok.exe http 8000
pause

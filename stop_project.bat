@echo off
echo ===============================
echo   Stopping Crop Recommender
echo ===============================

REM Close backend (uvicorn)
taskkill /IM "python.exe" /F >nul 2>&1

REM Close frontend (Node/Next.js)
taskkill /IM "node.exe" /F >nul 2>&1

echo ✅ All project servers stopped successfully.
pause

@echo off
echo ===============================
echo   Starting Crop Recommender
echo ===============================

REM --- Start backend minimized ---
start /min cmd /k "cd backend && venv\Scripts\activate && uvicorn main:app --reload"

REM Wait 4 seconds to let backend start
timeout /t 4 /nobreak >nul

REM --- Start frontend minimized ---
start /min cmd /k "cd frontend && npm run dev"

REM Wait a few seconds before opening the browser
timeout /t 6 /nobreak >nul

REM --- Open the frontend automatically in browser ---
start "" "http://localhost:3000"

echo ✅ Backend & Frontend started successfully!
echo 🌐 Browser opened at http://localhost:3000
pause

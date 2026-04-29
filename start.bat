@echo off
echo ================================================
echo   Matokeo RMS - Local Server
echo   Starting server at http://127.0.0.1:8080
echo ================================================
echo.
echo   Sign in with your Matokeo RMS admin account.
echo.
cd /d "%~dp0"
python manage.py runserver 8080
pause

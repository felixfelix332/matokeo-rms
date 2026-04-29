@echo off
echo ================================================
echo   Matokeo RMS - Reset Admin Password
echo ================================================
echo.
cd /d "%~dp0"
python manage.py reset_admin_password
echo.
pause

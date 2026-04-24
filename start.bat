@echo off
echo ================================================
echo   SCHOOL PORTAL - Command Center
echo   Starting server at http://127.0.0.1:8080
echo ================================================
echo.
echo   ADMIN LOGIN:    admin / admin123
echo   TEACHER LOGIN:  teacher1 / (school system password)
echo   STUDENT LOGIN:  Any admission number (e.g. JS801, JS903)
echo.
cd /d "%~dp0"
python manage.py runserver 8080
pause

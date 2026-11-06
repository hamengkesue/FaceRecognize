@echo off
cd /d "%~dp0"
echo ==============================================================
echo   Personal Laptop Face Guard - Registrasi Wajah Pemilik
echo ==============================================================
.\venv\Scripts\python.exe -m src.enroll
pause


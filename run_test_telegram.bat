@echo off
cd /d "%~dp0"
echo ==============================================================
echo   Uji Coba Notifikasi Bot Telegram
echo ==============================================================
.\venv\Scripts\python.exe test_telegram.py
pause


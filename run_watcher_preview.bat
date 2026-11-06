@echo off
cd /d "%~dp0"
echo ==============================================================
echo   Personal Laptop Face Guard - Preview Window (Debug Mode)
echo ==============================================================
echo [INFO] Menyalakan kamera dengan tampilan visual (Tekan ESC untuk keluar)...
.\venv\Scripts\python.exe -m src.watcher
pause


@echo off
cd /d "%~dp0"
echo ==============================================================
echo   Personal Laptop Face Guard - Background Service Startup
echo ==============================================================
echo [INFO] Menjalankan Face Guard di latar belakang (System Tray)...
echo [INFO] Periksa ikon perisai hijau di pojok kanan bawah dekat jam Windows.

IF EXIST "%~dp0venv\Scripts\pythonw.exe" (
    start "" "%~dp0venv\Scripts\pythonw.exe" -m src.tray_app
) ELSE IF EXIST "%~dp0venv\Scripts\python.exe" (
    start "" "%~dp0venv\Scripts\python.exe" -m src.tray_app
) ELSE (
    start "" pythonw -m src.tray_app
)

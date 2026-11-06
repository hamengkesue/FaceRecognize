@echo off
cd /d "%~dp0"
echo ==============================================================
echo   Mematikan Personal Laptop Face Guard (Background Service)
echo ==============================================================

taskkill /F /IM pythonw.exe 2>nul
if %ERRORLEVEL% equ 0 (
    echo [+] Layanan Face Guard (pythonw.exe) berhasil dihentikan.
) else (
    echo [-] Tidak ada proses Face Guard di latar belakang yang aktif.
)

echo.
echo Selesai.
pause

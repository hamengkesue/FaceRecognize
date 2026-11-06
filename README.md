# Personal Laptop Face Guard 🛡️

Sistem keamanan biometrik lokal untuk laptop (*Continuous Facial Authentication & Anti-Snooping*) berbasis **Python, InsightFace (ArcFace), MediaPipe, dan PostgreSQL (`pgvector`)**.

Sistem ini memantau secara proaktif di latar belakang (*background service*):
1. **Continuous Verification:** Memastikan laptop sedang dioperasikan oleh pemilik yang sah.
2. **Anti-Shoulder Surfing:** Mendeteksi jika ada orang lain yang mengintip dari belakang bahu dan memberikan peringatan *desktop toast*.
3. **Intruder Alert & Lock:** Jika orang lain mengoperasikan laptop selama 3 detik, sistem membunyikan alarm peringatan, mengambil foto bukti penyusup, mencatat ke PostgreSQL, mengirim bukti ke **Telegram** pemilik, dan **mengunci layar OS (`LockWorkStation`)**.
4. **Away Auto-Lock:** Jika pemilik meninggalkan laptop (0 wajah terdeteksi) selama lebih dari 30 detik, sistem otomatis mengunci layar.

---

## ⚡ Arsitektur & Peningkatan Performa (Improvements)

Berdasarkan analisis PRD dan panduan implementasi, sistem ini telah disempurnakan dengan rekomendasi terbaik:
- **In-Memory Embedding Caching:** Vektor wajah pemilik di-*load* ke RAM (`np.ndarray`) saat aplikasi dijalankan, sehingga pencocokan *Cosine Similarity* berjalan super cepat (< 0.05 ms) tanpa membebani PostgreSQL setiap *frame* (PRD Bagian 4.4 & 9.1).
- **Ketahanan Offline-First:** Sistem tetap 100% mampu mengenali pemilik dan mengunci layar saat penyusup datang meski laptop sedang offline atau Docker/PostgreSQL belum menyala (menggunakan *offline cache* lokal).
- **Windows DirectShow Acceleration (`cv2.CAP_DSHOW`):** Inisialisasi webcam instan (< 100ms) tanpa jeda MSMF dan tanpa error *frame grab*.
- **Passive Liveness & Anti-Spoofing:** MediaPipe Face Mesh dengan evaluasi *Eye Aspect Ratio (EAR)* per wajah untuk mencegah pengelabuan menggunakan foto statis HP.
- **Antrean Notifikasi Tertunda (Offline Queue Sync):** Foto penyusup yang belum terkirim karena laptop offline akan otomatis dikirim ke Telegram setelah koneksi internet kembali pulih.

---

## 📁 Struktur Direktori

```text
c:\Abyan\FaceRecognize/
├── docker-compose.yml         # Container PostgreSQL 16 + pgvector
├── init_db.sql                # Skema tabel owner, logs, dan indeks HNSW
├── requirements.txt           # Pustaka Python yang dibutuhkan
├── .env                       # File konfigurasi utama (DB & Telegram)
├── .env.example               # Template file konfigurasi
├── run_guard.bat              # Skrip 1-klik untuk Windows Startup
├── test_system.py             # Skrip diagnostik dan verifikasi sistem
├── assets/
│   └── sounds/                # Suara alarm peringatan (opsional: alert.wav)
├── logs/
│   └── intruders/             # Direktori penyimpanan foto bukti penyusup
└── src/
    ├── __init__.py
    ├── config.py              # Parser variabel lingkungan (.env)
    ├── database.py            # PostgreSQL + pgvector + In-Memory Caching
    ├── face_engine.py         # InsightFace (buffalo_s) & MediaPipe Liveness
    ├── notifier.py            # Telegram Bot API, Suara Alarm & OS Lock
    ├── enroll.py              # Wizard registrasi wajah pemilik (15 pose + centroid)
    ├── watcher.py             # Mesin pemantau continuous facial authentication
    └── tray_app.py            # Aplikasi System Tray Windows (Background)
```

---

## 🚀 Panduan Penggunaan Cepat

### 1. Menyalakan Database PostgreSQL
Jalankan container PostgreSQL (port `5433` untuk menghindari konflik dengan instalasi PostgreSQL lokal bawaan Windows):
```bash
docker compose up -d
```

### 2. Konfigurasi `.env`
Buka file `.env` dan masukkan data bot Telegram Anda:
```ini
TELEGRAM_BOT_TOKEN=1234567890:AAHxyz...
TELEGRAM_CHAT_ID=987654321
```

### 3. Registrasi Wajah Pemilik (`enroll.py`)
Jalankan skrip registrasi:
```bash
.\venv\Scripts\python.exe -m src.enroll
```
- Ikuti 5 instruksi posisi wajah (lurus, senyum, miring, mengetik, kacamata/jarak).
- Tekan **SPASI** untuk merekam tiap sampel (total 15 sampel + 1 centroid master).

### 4. Uji Coba Mode Preview Kamera (`watcher.py`)
```bash
.\venv\Scripts\python.exe -m src.watcher
```
- Kotak hijau `OWNER (0.60+)` menandakan Anda terverifikasi sebagai pemilik sah.
- Coba tutup wajah Anda atau minta rekan Anda melihat laptop selama 3 detik untuk menguji penguncian layar dan pengiriman foto ke Telegram.

### 5. Menjalankan di Background System Tray (`tray_app.py`)
```bash
.\venv\Scripts\python.exe -m src.tray_app
```
Ikon perisai hijau akan muncul di taskbar pojok kanan bawah (dekat jam Windows):
- Klik kanan ikon untuk **Jeda Proteksi (Pause)** atau **Keluar**.
- Klik ganda file `run_guard.bat` untuk menjalankan secara senyap (*background*) tanpa jendela terminal.

---

## ⚙️ Menjadikan Auto-Start saat Windows Dinyalakan
1. Tekan tombol **`Win + R`** di keyboard.
2. Ketik `shell:startup` lalu tekan **Enter**.
3. Buat *Shortcut* dari file `run_guard.bat` dan letakkan di dalam folder Startup tersebut.


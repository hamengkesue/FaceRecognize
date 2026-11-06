# Product Requirements Document (PRD): Personal Laptop Face Guard

**Nama Proyek:** Personal Laptop Face Guard (Continuous Facial Authentication & Anti-Snooping System)  
**Versi Dokumen:** 1.1 (PostgreSQL + pgvector Edition)  
**Target Platform:** Windows / Linux / macOS (Local Background Service)  

---

## 1. Ringkasan Eksekutif (Product Overview)

**Personal Laptop Face Guard** adalah sistem keamanan biometrik lokal yang bekerja di latar belakang (*background*) untuk memverifikasi secara berkala bahwa orang yang sedang mengoperasikan laptop adalah pemilik sah.

Berbeda dengan *Windows Hello* yang hanya melakukan autentikasi satu kali saat *login* awal, sistem ini melakukan **verifikasi berkelanjutan (*continuous authentication*)**. Jika orang lain mengambil alih laptop saat layar masih menyala, atau jika seseorang mengintip layar dari belakang bahu pemilik, sistem secara proaktif mengambil bukti foto, mencatat kejadian ke dalam database **PostgreSQL**, mengirim peringatan ke ponsel pemilik via Telegram, dan mengunci sistem operasi secara otomatis.

---

## 2. Rekomendasi Tech Stack

Arsitektur ini dirancang agar **ringan di CPU** (hemat baterai dan tidak membuat kipas laptop bising saat berjalan terus-menerus) serta menggunakan **PostgreSQL** untuk manajemen data relasional dan vektor biometrik yang tangguh:

| Komponen | Teknologi Utama | Alternatif | Alasan Pemilihan |
| :--- | :--- | :--- | :--- |
| **Core Language** | **Python 3.10+** | Go + OpenCV | Ekosistem *computer vision* paling matang dan mudah diintegrasikan dengan API sistem operasi. |
| **Face Detection** | **MediaPipe Face Detection** | RetinaFace / Haar Cascade | Eksekusi sangat cepat di CPU (hanya beberapa milidetik per *frame*) sebagai penyaring awal sebelum pengenalan wajah. |
| **Face Recognition** | **InsightFace (ArcFace)** via **ONNX Runtime** | `face_recognition` (dlib) | Menggunakan model *Buffalo_S/L* di atas ONNX yang jauh lebih akurat terhadap perubahan cahaya/sudut wajah dibanding `dlib`, serta mudah diinstal di Windows. |
| **Liveness / Anti-Spoofing** | **MediaPipe Face Mesh (EAR)** / **MiniFASNet** | Silent-Face-Anti-Spoofing | Mencegah orang mengakali webcam menggunakan foto wajah pemilik dari layar HP (deteksi kedipan mata / tekstur layar). |
| **Database & Vector Store** | **PostgreSQL 15+ (dengan `pgvector`)** | PostgreSQL (`FLOAT8[]`) | Mendukung penyimpanan vektor 512-dimensi secara *native*, memungkinkan perhitungan *Cosine Distance* langsung di level query database, serta siap diintegrasikan dengan Dashboard Web. |
| **Database Driver / ORM** | **psycopg (v3)** + **SQLAlchemy** | `asyncpg` | Driver PostgreSQL generasi terbaru untuk Python yang cepat, aman, dan mendukung tipe data vektor maupun `JSONB`. |
| **Alert & Notification** | **Telegram Bot API** + `plyer` | Discord Webhook / WhatsApp | Mengirim foto penyusup langsung ke HP secara *real-time* dalam hitungan detik + notifikasi *pop-up* lokal. |
| **OS Integration** | `ctypes` (Windows) | `pyobjc` (macOS) / `xdg` (Linux) | Memanggil perintah native `LockWorkStation()` untuk mengunci layar Windows seketika saat wajah asing terdeteksi. |
| **Dashboard UI (Opsional)** | **Next.js + FastAPI** | CustomTkinter / PyQt6 | Antarmuka web lokal yang terhubung ke PostgreSQL untuk melihat galeri foto penyusup, analitik waktu akses, dan mengatur sensitivitas kamera. |

---

## 3. Daftar Persiapan (Prerequisites Checklist)

Sebelum memulai penulisan kode, pastikan hal-hal berikut sudah disiapkan:

### A. Data & Aset Wajah
- [ ] **Dataset Foto Wajah Pribadi (15 – 20 Foto):**
  - Variasi ekspresi (netral, tersenyum, fokus mengetik).
  - Variasi aksesoris (memakai kacamata vs lepas kacamata, memakai topi/headset).
  - Variasi pencahayaan (kondisi ruangan terang, redup/malam hari dengan pantulan cahaya layar laptop).
  - Variasi sudut pandang (lurus ke kamera, agak menunduk, menoleh sedikit ke kiri/kanan).

### B. Database PostgreSQL
- [ ] **Instalasi PostgreSQL Server (Lokal atau Docker):**
  - Buat database khusus bernama `face_guard_db`.
  - Aktifkan ekstensi `vector` (*pgvector*) jika ingin melakukan komparasi kemiripan wajah langsung melalui SQL, atau gunakan tipe array standar `FLOAT8[]`.

### C. Environment & Library Python
- [ ] **Instalasi Python 3.10+ & Virtual Environment (`venv`)**
- [ ] **Instalasi Paket Utama:**
  ```bash
  pip install opencv-python insightface onnxruntime mediapipe numpy requests plyer pystray pillow psycopg[binary] pgvector sqlalchemy python-dotenv
  ```

### D. Integrasi Eksternal
- [ ] **Bot Telegram & Chat ID:**
  - Buat bot baru melalui `@BotFather` di Telegram dan simpan `BOT_TOKEN` di dalam file `.env`.
  - Dapatkan `CHAT_ID` akun Telegram pribadi untuk tujuan pengiriman foto penyusup.
- [ ] **File Audio Peringatan (`.wav` / `.mp3`):**
  - Suara alarm singkat atau efek suara peringatan untuk memberikan efek kejut pada pemegang laptop yang tidak sah.

---

## 4. Analisis Skenario & Fitur Tambahan (Edge-Case Enhancements)

Untuk memastikan sistem nyaman dipakai sehari-hari dan tidak mengganggu produktivitas pemilik, 4 mekanisme berikut wajib diimplementasikan:

1. **Grace Period & Debouncing (Pencegahan False Alarm):**  
   Kamera tidak boleh langsung mengunci layar hanya karena 1 *frame* wajah pemilik buram (misalnya saat sedang mengucek mata, minum, atau menoleh sebentar). Sistem harus memvalidasi ketidakcocokan selama **3–5 detik berturut-turut** sebelum memicu status bahaya.
2. **Shoulder Surfing Mode (Deteksi Pengintip di Belakang):**  
   Membedakan antara kondisi **"Laptop dipegang orang lain"** (hanya ada 1 wajah asing) dengan **"Ada yang mengintip dari belakang"** (terdeteksi wajah pemilik + wajah asing dalam satu *frame*).
3. **Passive Anti-Spoofing (Liveness Check):**  
   Menolak autentikasi jika wajah yang terdeteksi tidak menunjukkan tanda kehidupan (tidak ada perubahan rasio mata/kedipan atau terdeteksi pantulan bingkai layar HP).
4. **Adaptive Duty-Cycle Polling & In-Memory Caching:**  
   - Vektor wajah pemilik yang ada di PostgreSQL akan di-*load* ke dalam memori (RAM) saat aplikasi pertama kali dijalankan agar kamera tidak perlu melakukan *query* ke PostgreSQL setiap milidetik. PostgreSQL hanya diakses saat registrasi wajah baru atau saat menulis *log* kejadian keamanan.
   - Saat pemilik sudah terverifikasi aman (`AUTHORIZED`), sistem menurunkan frekuensi pemindaian menjadi 1 *frame* setiap 3 detik untuk menghemat baterai.

---

## 5. Spesifikasi Kebutuhan Fungsional (Functional Requirements)

| ID | Modul | Deskripsi Kebutuhan Teknis | Prioritas |
| :--- | :--- | :--- | :--- |
| **FR-01** | **Face Enrollment (Registrasi)** | Sistem menyediakan skrip `enroll.py` untuk memindai 15–20 foto wajah pemilik, mengekstrak *feature vector* (512-dimensi via ArcFace), dan menyimpannya ke tabel `owner_embeddings` di PostgreSQL. | **P0 (Wajib)** |
| **FR-02** | **Continuous Verification** | Sistem mengambil *frame* dari webcam secara berkala, mendeteksi wajah, dan menghitung **Cosine Similarity** antara wajah di kamera dengan *embedding* pemilik. Jika skor kemiripan $\ge 0.50$, status dinyatakan **Authorized**. | **P0 (Wajib)** |
| **FR-03** | **Intruder Detection & Alert** | Jika terdeteksi wajah dengan skor kemiripan $< 0.50$ secara konsisten selama 3 detik:<br>1. Memotret wajah penyusup (*snapshot*).<br>2. Menyimpan *record* beserta metadata ke PostgreSQL.<br>3. Mengirim foto + *timestamp* ke Telegram pemilik.<br>4. Mengunci layar OS (*Lock Screen*) secara otomatis. | **P0 (Wajib)** |
| **FR-04** | **Shoulder Surfing Alert (Anti-Intip)** | Jika di dalam 1 *frame* terdeteksi **Wajah Pemilik + Wajah Asing** selama $> 2$ detik, sistem mencatat *event* `SNOOPING_WARNING` ke PostgreSQL dan menampilkan *pop-up toast* peringatan di sudut layar tanpa mengunci sesi kerja. | **P1 (Tinggi)** |
| **FR-05** | **Auto-Lock saat Kosong (Away Lock)** | Jika kamera tidak mendeteksi wajah sama sekali (`0 face`) selama lebih dari 30 detik, sistem mencatat status `USER_AWAY` ke PostgreSQL dan otomatis mengunci layar laptop secara senyap. | **P1 (Tinggi)** |
| **FR-06** | **Passive Liveness Check** | Memeriksa rasio kedipan mata (*Eye Aspect Ratio* / EAR) untuk memastikan wajah di depan kamera adalah manusia hidup, bukan foto statis dari layar ponsel. | **P2 (Menengah)** |
| **FR-07** | **Audit Log & Analytics Dashboard** | Menyimpan riwayat lengkap ke PostgreSQL (termasuk vektor wajah penyusup untuk pengelompokan penyusup berulang) yang dapat dipantau melalui antarmuka Web/Dashboard. | **P2 (Menengah)** |

---

## 6. Logika Matematis & State Machine Sistem

### A. Rumus Perhitungan Kemiripan Wajah (Cosine Similarity)
Setiap wajah yang dideteksi oleh InsightFace akan diubah menjadi vektor berdimensi 512 ($\mathbf{A}$ untuk vektor pemilik di database, dan $\mathbf{B}$ untuk vektor wajah yang tertangkap kamera saat ini). Tingkat kemiripan dihitung menggunakan persamaan:

$$\text{Cosine Similarity} = \frac{\mathbf{A} \cdot \mathbf{B}}{\|\mathbf{A}\| \|\mathbf{B}\|} = \frac{\sum_{i=1}^{512} A_i B_i}{\sqrt{\sum_{i=1}^{512} A_i^2} \sqrt{\sum_{i=1}^{512} B_i^2}}$$

- Jika nilai $\ge 0.50$: Dianggap **Wajah Pemilik (Cocok)**.
- Jika nilai $< 0.50$: Dianggap **Wajah Asing (Tidak Cocok)**.

### B. Tabel Keputusan State Machine

| Kondisi Kamera | Durasi Validasi | Status Sistem | Aksi yang Dieksekusi |
| :--- | :--- | :--- | :--- |
| **1 Wajah (Cocok = Kamu)** | Instan | `AUTHORIZED` | Reset semua *timer* bahaya. Kembali ke mode *idle polling* (cek tiap 3 detik). |
| **1 Wajah (Tidak Cocok = Orang Lain)** | Bertahan $> 3\text{ detik}$ | `INTRUDER_ALERT` | Simpan foto ke `logs/intruders/`, *insert* data ke PostgreSQL, bunyikan alarm, kirim foto ke Telegram, lalu jalankan perintah `LockWorkStation()`. |
| **$\ge 2$ Wajah (1 Kamu + $\ge 1$ Orang Lain)** | Bertahan $> 2\text{ detik}$ | `SNOOPING_WARNING` | *Insert* log ke PostgreSQL dan tampilkan notifikasi sudut layar ("*Awas, ada orang di belakang Anda!*"). |
| **0 Wajah (Kursi Kosong)** | Bertahan $> 30\text{ detik}$ | `USER_AWAY` | *Insert* log `USER_AWAY` ke PostgreSQL dan jalankan `LockWorkStation()` secara senyap. |

---

## 7. Desain Skema Database (PostgreSQL)

Penggunaan PostgreSQL memberikan keuntungan besar: kita bisa menyimpan vektor 512-dimensi menggunakan ekstensi `pgvector` (atau `FLOAT8[]`) serta menyimpan metadata tambahan dalam format `JSONB` (seperti koordinat kotak wajah *bounding box* atau tingkat kecerahan kamera).

```sql
-- Aktifkan ekstensi pgvector & uuid (Jalankan sekali sebagai superuser)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Tabel Profil & Embedding Wajah Pemilik
CREATE TABLE owner_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_name VARCHAR(100) NOT NULL DEFAULT 'Owner',
    condition_label VARCHAR(50) NOT NULL, -- contoh: 'terang_kacamata', 'redup_malam', 'centroid_utama'
    embedding vector(512) NOT NULL,       -- Vektor ArcFace 512-dimensi (gunakan FLOAT8[] jika tanpa pgvector)
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tipe Enum untuk Jenis Kejadian Keamanan
CREATE TYPE security_event_type AS ENUM (
    'INTRUDER_ALERT',
    'SNOOPING_WARNING',
    'USER_AWAY',
    'SPOOF_ATTEMPT'
);

-- 3. Tabel Log Kejadian Keamanan & Bukti Penyusup
CREATE TABLE security_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type security_event_type NOT NULL,
    similarity_score REAL,                -- Skor kemiripan tertinggi saat kejadian (misal: 0.18)
    detected_faces_count SMALLINT NOT NULL DEFAULT 1,
    intruder_embedding vector(512),       -- Menyimpan vektor wajah penyusup untuk mengenali penyusup yang sama di kemudian hari
    snapshot_path TEXT,                   -- Path lokal menuju file foto bukti penyusup
    metadata JSONB DEFAULT '{}'::jsonb,   -- Menyimpan info tambahan: {"bbox": [x,y,w,h], "lighting": "low", "os_locked": true}
    telegram_notified BOOLEAN DEFAULT FALSE,
    detected_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 4.Tabel Konfigurasi Sistem Dinamis (Bisa diubah dari Dashboard UI tanpa restart aplikasi)
CREATE TABLE system_settings (
    key VARCHAR(50) PRIMARY KEY,
    value VARCHAR(255) NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Data Awal Konfigurasi Sistem
INSERT INTO system_settings (key, value, description) VALUES
('similarity_threshold', '0.50', 'Batas minimum Cosine Similarity agar diakui sebagai pemilik'),
('intruder_grace_period_sec', '3', 'Durasi (detik) wajah asing bertahan sebelum memicu Lock Screen'),
('away_lock_timeout_sec', '30', 'Durasi (detik) kursi kosong sebelum laptop mengunci otomatis'),
('idle_polling_interval_sec', '3', 'Jeda waktu pengambilan frame saat kondisi aman (hemat baterai)');

-- Indexing untuk mempercepat query Dashboard & Pencarian Vektor
CREATE INDEX idx_security_logs_event_time ON security_logs (event_type, detected_at DESC);
```

---

## 8. Struktur Direktori Proyek (Project Structure)

Agar kode mudah dikelola dan siap dikembangkan ke tahap Dashboard, gunakan struktur folder modular berikut:

```text
face-guard-system/
├── .env                        # Menyimpan kredensial PostgreSQL (DB_URI) & Telegram (BOT_TOKEN, CHAT_ID)
├── requirements.txt            # Daftar dependensi library Python
├── config/
│   └── database.py             # Konfigurasi koneksi PostgreSQL (SQLAlchemy / psycopg3 pool)
├── core/
│   ├── detector.py             # Inisialisasi InsightFace (ONNX) & ekstraksi vektor 512-D
│   ├── liveness.py             # Deteksi kedipan mata (MediaPipe EAR) untuk anti-spoofing
│   └── verifier.py             # Perhitungan Cosine Similarity & pencocokan dengan cache memori
├── services/
│   ├── notifier.py             # Pengiriman foto & pesan peringatan ke Telegram Bot API (Asynchronous)
│   ├── os_controller.py        # Perintah native Lock Screen (Windows/Linux/macOS) & pemutar audio alarm
│   └── logger_repo.py          # Operasi CRUD untuk menyimpan log penyusup & foto ke PostgreSQL
├── assets/
│   ├── owner_photos/           # Folder tempat menaruh 15-20 foto wajah kamu untuk proses registrasi
│   └── sounds/
│       └── alert.wav           # Suara sirine/peringatan saat penyusup terdeteksi
├── logs/
│   └── intruders/              # Folder penyimpanan otomatis hasil jepretan wajah penyusup (.jpg)
├── enroll.py                   # Skrip CLI untuk memindai folder owner_photos/ & menyimpan vektor ke PostgreSQL
└── watcher.py                  # Aplikasi utama (Background Daemon / System Tray) yang memantau webcam
```

---

## 9. Kebutuhan Non-Fungsional (Non-Functional Requirements)

1. **Performa & Resource:**
   - Penggunaan CPU di latar belakang harus berada di bawah **5–8%** saat mode *idle polling*.
   - Penggunaan koneksi PostgreSQL menggunakan *Connection Pooling* dan *In-Memory Vector Caching* agar tidak membebani I/O disk setiap kali kamera memindai wajah.
2. **Kecepatan Respons (Latency):**
   - Waktu inferensi per *frame* (Deteksi + Ekstraksi Vektor + Komparasi Cosine) harus selesai dalam waktu kurang dari **100 ms** di atas CPU standar.
3. **Ketahanan Offline (Offline-First):**
   - Seluruh proses pengenalan wajah, pencatatan ke PostgreSQL lokal, dan penguncian layar **wajib berjalan 100% tanpa koneksi internet**.
   - Jika laptop sedang tidak terhubung ke Wi-Fi saat penyusup terdeteksi, status `telegram_notified` di PostgreSQL akan bernilai `FALSE`. *Background worker* akan otomatis mengirim foto yang tertunda begitu koneksi internet kembali menyambung.
4. **Privasi & Keamanan Data:**
   - *Frame* kamera saat kondisi aman (`AUTHORIZED`) langsung dihapus dari memori (*RAM buffer*) dan tidak pernah disimpan ke *hardisk*. Hanya *frame* `INTRUDER_ALERT` dan `SNOOPING_WARNING` yang disimpan sebagai barang bukti.

---

## 10. Roadmap Pengerjaan (Implementation Phases)

- **Fase 1 — Database Setup & Face Enrollment:**  
  Menyiapkan database PostgreSQL (`face_guard_db`), menjalankan skrip SQL di atas, dan membuat `enroll.py` untuk mengekstrak vektor dari 15–20 foto wajahmu ke dalam tabel `owner_embeddings`.
- **Fase 2 — Core Watcher & OS Lock:**  
  Membangun `watcher.py` yang membaca vektor dari PostgreSQL, memvalidasi wajah lewat webcam secara *real-time*, menerapkan *timer* 3 detik, menyimpan bukti penyusup ke tabel `security_logs`, mengirim *alert* Telegram, dan mengunci layar Windows.
- **Fase 3 — Background Service & System Tray:**  
  Menyembunyikan jendela kamera agar berjalan senyap di *System Tray* Windows (dekat ikon jam) beserta fitur *retry* pengiriman Telegram otomatis jika sempat *offline*.
- **Fase 4 — Dashboard Monitoring Web (Opsional):**  
  Membangun antarmuka menggunakan **Next.js + FastAPI** yang membaca data langsung dari PostgreSQL untuk menampilkan galeri foto penyusup, kemiripan vektor penyusup berulang, serta pengaturan *threshold* secara visual.
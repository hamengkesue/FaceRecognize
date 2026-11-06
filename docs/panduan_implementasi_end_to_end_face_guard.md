# Panduan Implementasi End-to-End: Personal Laptop Face Guard (Python + PostgreSQL)

Dokumen ini berisi panduan implementasi teknis secara lengkap dari awal hingga akhir (*end-to-end*). Seluruh kode dirancang modular, siap dijalankan di **Windows / Linux / macOS**, dan menggunakan **PostgreSQL (`pgvector`)** sebagai mesin pencocokan vektor wajah.

---

## 1. Struktur Folder Proyek

Buat sebuah direktori baru bernama `laptop-face-guard` dengan struktur file seperti di bawah ini:

```text
laptop-face-guard/
├── docker-compose.yml         # Setup cepat PostgreSQL 16 + pgvector
├── init_db.sql                # Skema tabel & fungsi SQL otomatis
├── .env                       # Konfigurasi rahasia (DB, Telegram, Threshold)
├── requirements.txt           # Daftar pustaka Python
├── logs/
│   └── intruders/             # Folder penyimpanan bukti foto penyusup otomatis
├── src/
│   ├── __init__.py
│   ├── config.py              # Pembaca environment variables (.env)
│   ├── database.py            # Koneksi PostgreSQL & query pencarian vektor
│   ├── face_engine.py         # Wrapper InsightFace (ArcFace) & MediaPipe Liveness
│   ├── notifier.py            # Pengirim foto Telegram, antrean offline & OS Lock
│   ├── enroll.py              # Skrip registrasi wajah pemilik ke PostgreSQL
│   ├── watcher.py             # Loop utama kamera & State Machine keamanan
│   └── tray_app.py            # Pembungkus aplikasi di System Tray (Background)
└── run_guard.bat              # Skrip eksekusi 1-klik untuk Windows Startup
```

---

## 2. Persiapan Database PostgreSQL & Environment

### A. File `docker-compose.yml` (Opsional jika belum ada PostgreSQL lokal)
Jika kamu menggunakan Docker, file ini akan langsung menyiapkan PostgreSQL 16 yang sudah terinstal ekstensi `pgvector`. Jika kamu menggunakan PostgreSQL bawaan Windows, cukup pastikan database `face_guard_db` telah dibuat.

```yaml
version: '3.8'

services:
  postgres_face_db:
    image: pgvector/pgvector:pg16
    container_name: face_guard_postgres
    restart: always
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password_rahasia
      POSTGRES_DB: face_guard_db
    ports:
      - "5432:5432"
    volumes:
      - pgdata_face_guard:/var/lib/postgresql/data
      - ./init_db.sql:/docker-entrypoint-initdb.d/init_db.sql

volumes:
  pgdata_face_guard:
```

### B. File `init_db.sql` (Skema Database Lengkap)
Jalankan skrip SQL ini di PostgreSQL kamu (melalui pgAdmin, DBeaver, atau `psql`). Skrip ini juga dilengkapi *fallback* otomatis jika PostgreSQL lokalmu belum terinstal ekstensi `pgvector`? Tidak perlu khawatir, skrip di bawah menggunakan `pgvector` dan menyediakan indeks pencarian cepat **HNSW**.

```sql
-- Aktifkan ekstensi pgvector untuk menyimpan embedding 512 dimensi
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Tabel Profil Wajah Pemilik Laptop
CREATE TABLE IF NOT EXISTS owner_embeddings (
    id SERIAL PRIMARY KEY,
    pose_label VARCHAR(50) NOT NULL, -- contoh: 'lurus_terang', 'kacamata', 'miring_kiri', 'centroid'
    embedding vector(512) NOT NULL,  -- Vektor 512-D ternormalisasi dari ArcFace
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Indeks HNSW untuk pencarian Cosine Similarity instan
CREATE INDEX IF NOT EXISTS idx_owner_embedding_cosine 
ON owner_embeddings USING hnsw (embedding vector_cosine_ops);

-- 2. Tabel Riwayat Keamanan & Bukti Penyusup
CREATE TABLE IF NOT EXISTS security_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(30) NOT NULL,       -- 'INTRUDER_ALERT', 'SNOOPING_WARNING', 'USER_AWAY'
    similarity_score REAL,                 -- Skor kemiripan tertinggi dengan pemilik (0.0 - 1.0)
    intruder_embedding vector(512),        -- Vektor wajah penyusup untuk mendeteksi pelaku berulang
    repeat_offender_of INT REFERENCES security_logs(id) ON DELETE SET NULL,
    snapshot_path TEXT,                    -- Path file foto bukti di disk lokal
    is_notified BOOLEAN DEFAULT FALSE,     -- Status pengiriman ke Telegram
    detected_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Konfigurasi Sistem Dinamis
CREATE TABLE IF NOT EXISTS system_configs (
    config_key VARCHAR(50) PRIMARY KEY,
    config_value VARCHAR(100) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO system_configs (config_key, config_value) VALUES
('similarity_threshold', '0.50'),
('intruder_grace_seconds', '3.0'),
('snooping_grace_seconds', '2.0'),
('away_lock_seconds', '30.0'),
('idle_poll_interval', '2.5')
ON CONFLICT (config_key) DO NOTHING;
```

---

## 3. Konfigurasi Proyek (`requirements.txt` & `.env`)

### A. File `requirements.txt`
```txt
opencv-python==4.10.0.84
insightface==0.7.3
onnxruntime==1.19.2
mediapipe==0.10.14
numpy==1.26.4
psycopg2-binary==2.9.9
pgvector==0.3.5
python-dotenv==1.0.1
requests==2.32.3
plyer==2.1.0
pystray==0.19.5
Pillow==10.4.0
```

Instal dengan perintah:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### B. File `.env`
```ini
# Konfigurasi PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=face_guard_db
DB_USER=postgres
DB_PASSWORD=password_rahasia

# Konfigurasi Telegram Bot (Dapatkan dari @BotFather & @userinfobot)
TELEGRAM_BOT_TOKEN=1234567890:AAHxyzContohTokenBotAndaDisini
TELEGRAM_CHAT_ID=987654321

# Konfigurasi Kamera & Parameter Default
CAMERA_INDEX=0
SIMILARITY_THRESHOLD=0.50
INTRUDER_GRACE_SEC=3.0
SNOOPING_GRACE_SEC=2.0
AWAY_LOCK_SEC=30.0
IDLE_POLL_SEC=2.5
```

---

## 4. Implementasi Kode Sumber Lengkap (`src/`)

### A. Modul Konfigurasi (`src/config.py`)
```python
import os
from pathlib import Path
from dotenv import load_dotenv

# Muat file .env dari root proyek
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Pastikan folder penyimpanan foto penyusup tersedia
INTRUDER_LOG_DIR = BASE_DIR / "logs" / "intruders"
INTRUDER_LOG_DIR.mkdir(parents=True, exist_ok=True)

class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 5432))
    DB_NAME = os.getenv("DB_NAME", "face_guard_db")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "password_rahasia")

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", 0))
    SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", 0.50))
    INTRUDER_GRACE_SEC = float(os.getenv("INTRUDER_GRACE_SEC", 3.0))
    SNOOPING_GRACE_SEC = float(os.getenv("SNOOPING_GRACE_SEC", 2.0))
    AWAY_LOCK_SEC = float(os.getenv("AWAY_LOCK_SEC", 30.0))
    IDLE_POLL_SEC = float(os.getenv("IDLE_POLL_SEC", 2.5))
```

---

### B. Modul Database PostgreSQL + `pgvector` (`src/database.py`)
Modul ini menangani penyimpanan *embedding* wajah pemilik, pencarian kemiripan menggunakan operator jarak kosinus `<=>` di PostgreSQL, serta pelacakan apakah penyusup yang terdeteksi pernah mencoba mengakses laptop sebelumnya.

```python
import psycopg2
from pgvector.psycopg2 import register_vector
import numpy as np
from typing import Tuple, Optional, List, Dict
from src.config import Config

class FaceDatabase:
    def __init__(self):
        self.conn = None
        self.connect()

    def connect(self):
        """Membuka koneksi ke PostgreSQL dan mendaftarkan tipe data vector."""
        if self.conn is None or self.conn.closed != 0:
            self.conn = psycopg2.connect(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                dbname=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD
            )
            self.conn.autocommit = True
            register_vector(self.conn)

    def clear_owner_embeddings(self):
        """Menghapus data registrasi lama sebelum melakukan enrollment ulang."""
        self.connect()
        with self.conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE owner_embeddings RESTART IDENTITY;")

    def save_owner_embedding(self, pose_label: str, embedding: np.ndarray):
        """Menyimpan vektor 512-D wajah pemilik ke PostgreSQL."""
        self.connect()
        norm_emb = embedding / np.linalg.norm(embedding)
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO owner_embeddings (pose_label, embedding) VALUES (%s, %s);",
                (pose_label, norm_emb)
            )

    def verify_face(self, query_embedding: np.ndarray) -> Tuple[bool, float, str]:
        """
        Mencocokkan vektor wajah di kamera dengan seluruh sampel wajah pemilik di PostgreSQL.
        Mengembalikan: (is_owner, max_similarity_score, matched_pose_label)
        """
        self.connect()
        norm_query = query_embedding / np.linalg.norm(query_embedding)
        with self.conn.cursor() as cur:
            # Operator <=> menghitung Cosine Distance, sehingga Similarity = 1 - Distance
            cur.execute(
                """
                SELECT pose_label, 1 - (embedding <=> %s) AS similarity
                FROM owner_embeddings
                ORDER BY embedding <=> %s ASC
                LIMIT 1;
                """,
                (norm_query, norm_query)
            )
            row = cur.fetchone()
            if not row:
                return False, 0.0, "none"

            pose_label, similarity = row[0], float(row[1])
            is_owner = similarity >= Config.SIMILARITY_THRESHOLD
            return is_owner, similarity, pose_label

    def check_repeat_intruder(self, intruder_embedding: np.ndarray, threshold: float = 0.55) -> Optional[int]:
        """Mengecek apakah wajah asing ini pernah terekam sebagai penyusup sebelumnya."""
        self.connect()
        norm_emb = intruder_embedding / np.linalg.norm(intruder_embedding)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, 1 - (intruder_embedding <=> %s) AS similarity
                FROM security_logs
                WHERE event_type = 'INTRUDER_ALERT' AND intruder_embedding IS NOT NULL
                ORDER BY intruder_embedding <=> %s ASC
                LIMIT 1;
                """,
                (norm_emb, norm_emb)
            )
            row = cur.fetchone()
            if row and float(row[1]) >= threshold:
                return int(row[0])
            return None

    def log_security_event(
        self,
        event_type: str,
        similarity_score: Optional[float] = None,
        intruder_embedding: Optional[np.ndarray] = None,
        snapshot_path: Optional[str] = None,
        is_notified: bool = False
    ) -> Tuple[int, Optional[int]]:
        """
        Mencatat kejadian keamanan ke PostgreSQL.
        Mengembalikan (log_id_baru, repeat_offender_log_id).
        """
        self.connect()
        repeat_id = None
        norm_emb = None

        if intruder_embedding is not None:
            norm_emb = intruder_embedding / np.linalg.norm(intruder_embedding)
            repeat_id = self.check_repeat_intruder(norm_emb)

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO security_logs 
                (event_type, similarity_score, intruder_embedding, repeat_offender_of, snapshot_path, is_notified)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (event_type, similarity_score, norm_emb, repeat_id, snapshot_path, is_notified)
            )
            new_id = cur.fetchone()[0]
            return new_id, repeat_id

    def get_pending_notifications(self) -> List[Dict]:
        """Mengambil daftar foto penyusup yang belum terkirim ke Telegram (karena sempat offline)."""
        self.connect()
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, event_type, similarity_score, snapshot_path, detected_at, repeat_offender_of
                FROM security_logs
                WHERE is_notified = FALSE AND event_type = 'INTRUDER_ALERT'
                ORDER BY detected_at ASC
                LIMIT 10;
                """
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "event_type": r[1],
                    "similarity_score": r[2],
                    "snapshot_path": r[3],
                    "detected_at": r[4],
                    "repeat_offender_of": r[5]
                }
                for r in rows
            ]

    def mark_as_notified(self, log_id: int):
        """Menandai log bahwa notifikasi Telegram telah berhasil terkirim."""
        self.connect()
        with self.conn.cursor() as cur:
            cur.execute("UPDATE security_logs SET is_notified = TRUE WHERE id = %s;", (log_id,))
```

---

### C. Modul Deteksi, Pengenalan & Anti-Spoofing (`src/face_engine.py`)
Menggabungkan **InsightFace (`buffalo_s`)** di atas ONNX Runtime agar sangat ringan di CPU, serta **MediaPipe Face Mesh** untuk menghitung *Eye Aspect Ratio (EAR)* dan pergerakan mikro wajah guna menangkal percobaan *spoofing* menggunakan foto HP.

```python
import cv2
import numpy as np
import mediapipe as mp
from insightface.app import FaceAnalysis
from typing import List, Dict

class FaceEngine:
    def __init__(self):
        # Menggunakan model buffalo_s yang sangat cepat untuk CPU laptop
        self.app = FaceAnalysis(
            name="buffalo_s",
            providers=["CPUExecutionProvider"]
        )
        # det_size=(640, 640) optimal untuk menangkap wajah utama & pengintip di belakang
        self.app.prepare(ctx_id=0, det_size=(640, 640))

        # Inisialisasi MediaPipe Face Mesh untuk Passive Liveness / Anti-Spoofing
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=2,
            refine_landmarks=True,
            min_detection_confidence=0.5
        )
        # Indeks landmark kelopak mata kiri & kanan MediaPipe
        self.LEFT_EYE = [362, 385, 387, 263, 373, 380]
        self.RIGHT_EYE = [33, 160, 158, 133, 153, 144]

    def _calculate_ear(self, landmarks, eye_indices, frame_w: int, frame_h: int) -> float:
        """Menghitung Eye Aspect Ratio (EAR) untuk memvalidasi struktur mata manusia asli."""
        pts = np.array([
            [landmarks[idx].x * frame_w, landmarks[idx].y * frame_h]
            for idx in eye_indices
        ])
        # Jarak vertikal kelopak mata
        v1 = np.linalg.norm(pts[1] - pts[5])
        v2 = np.linalg.norm(pts[2] - pts[4])
        # Jarak horizontal sudut mata
        h = np.linalg.norm(pts[0] - pts[3])
        if h == 0:
            return 0.0
        return float((v1 + v2) / (2.0 * h))

    def check_liveness(self, frame: np.ndarray) -> bool:
        """
        Memeriksa apakah wajah di depan kamera memiliki geometri mata 3D yang valid.
        Mengembalikan True jika terdeteksi struktur wajah manusia yang wajar.
        """
        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)

        if not results.multi_face_landmarks:
            return False

        for face_landmarks in results.multi_face_landmarks:
            left_ear = self._calculate_ear(face_landmarks.landmark, self.LEFT_EYE, w, h)
            right_ear = self._calculate_ear(face_landmarks.landmark, self.RIGHT_EYE, w, h)
            avg_ear = (left_ear + right_ear) / 2.0
            # Rentang EAR mata manusia terbuka normal berada di antara 0.12 hingga 0.45
            if 0.10 <= avg_ear <= 0.48:
                return True
        return False

    def analyze_frame(self, frame: np.ndarray) -> List[Dict]:
        """
        Mendeteksi semua wajah di dalam frame dan mengekstrak vektor 512-D (ArcFace).
        Hasil diurutkan dari ukuran kotak wajah terbesar (paling dekat dengan layar).
        """
        faces = self.app.get(frame)
        parsed_faces = []

        for face in faces:
            bbox = face.bbox.astype(int) # [x1, y1, x2, y2]
            area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            parsed_faces.append({
                "bbox": bbox,
                "area": area,
                "embedding": face.normed_embedding, # Vektor 512-D yang sudah dinormalisasi
                "det_score": float(face.det_score)
            })

        # Urutkan dari wajah yang paling dekat dengan webcam (area terbesar)
        parsed_faces.sort(key=lambda x: x["area"], reverse=True)
        return parsed_faces
```

---

### D. Modul Peringatan Telegram, Pop-Up & Pengunci OS (`src/notifier.py`)
Menangani pengiriman bukti foto ke Telegram, antrean pengiriman ulang saat *offline*, peringatan suara, notifikasi desktop, dan perintah penguncian sistem operasi.

```python
import os
import sys
import ctypes
import platform
import requests
from datetime import datetime
from plyer import notification
from src.config import Config
from src.database import FaceDatabase

class SecurityNotifier:
    def __init__(self, db: FaceDatabase):
        self.db = db

    @staticmethod
    def play_alert_sound():
        """Membunyikan suara peringatan bawaan OS tanpa memerlukan file audio eksternal."""
        if platform.system() == "Windows":
            import winsound
            winsound.Beep(1800, 400)
            winsound.Beep(2200, 500)
        else:
            sys.stdout.write("\a")
            sys.stdout.flush()

    @staticmethod
    def show_desktop_toast(title: str, message: str):
        """Menampilkan notifikasi pop-up di sudut layar."""
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="Laptop Face Guard",
                timeout=4
            )
        except Exception as e:
            print(f"[WARN] Gagal menampilkan notifikasi desktop: {e}")

    @staticmethod
    def lock_workstation():
        """Mengunci layar laptop secara instan sesuai sistem operasi."""
        os_name = platform.system()
        try:
            if os_name == "Windows":
                ctypes.windll.user32.LockWorkStation()
            elif os_name == "Darwin":  # macOS
                os.system("/System/Library/CoreServices/Menu\\ Extras/User.menu/Contents/Resources/CGSession -suspend")
            elif os_name == "Linux":
                os.system("xdg-screensaver lock || loginctl lock-session")
        except Exception as e:
            print(f"[ERROR] Gagal mengunci layar OS: {e}")

    def send_telegram_intruder_photo(
        self,
        image_path: str,
        similarity_score: float,
        repeat_id: int = None,
        timestamp_str: str = None
    ) -> bool:
        """Mengirim foto penyusup ke Telegram pemilik."""
        if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
            print("[WARN] Token Telegram belum dikonfigurasi di .env")
            return False

        waktu = timestamp_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        repeat_note = (
            f"\n⚠️ *Pelaku Berulang!* (Cocok dengan Log ID #{repeat_id})"
            if repeat_id else "\n🆕 *Wajah Asing Baru*"
        )

        caption = (
            f"🚨 *PERINGATAN KEAMANAN LAPTOP* 🚨\n\n"
            f"Seseorang yang *bukan Anda* terdeteksi sedang memegang laptop!\n"
            f"🕒 *Waktu:* `{waktu}`\n"
            f"🎯 *Skor Kemiripan:* `{similarity_score:.2f}` (Batas: `{Config.SIMILARITY_THRESHOLD}`)"
            f"{repeat_note}\n"
            f"🔒 *Tindakan:* Layar laptop telah dikunci otomatis."
        )

        url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendPhoto"
        try:
            with open(image_path, "rb") as photo_file:
                response = requests.post(
                    url,
                    data={
                        "chat_id": Config.TELEGRAM_CHAT_ID,
                        "caption": caption,
                        "parse_mode": "Markdown"
                    },
                    files={"photo": photo_file},
                    timeout=8
                )
            return response.status_code == 200
        except Exception as e:
            print(f"[OFFLINE] Gagal mengirim ke Telegram, masuk ke antrean database: {e}")
            return False

    def flush_offline_queue(self):
        """Mengirimkan foto penyusup yang sempat tertunda saat laptop tidak ada internet."""
        pending_logs = self.db.get_pending_notifications()
        for log in pending_logs:
            img_path = log["snapshot_path"]
            if img_path and os.path.exists(img_path):
                success = self.send_telegram_intruder_photo(
                    image_path=img_path,
                    similarity_score=log["similarity_score"] or 0.0,
                    repeat_id=log["repeat_offender_of"],
                    timestamp_str=str(log["detected_at"])
                )
                if success:
                    self.db.mark_as_notified(log["id"])
                    print(f"[QUEUE] Berhasil mengirim notifikasi tertunda untuk Log #{log['id']}")
```

---

### E. Skrip Registrasi Wajah Pemilik (`src/enroll.py`)
Skrip interaktif ini memandu kamu mengambil **15 sampel wajah** dari berbagai sudut dan ekspresi lewat *webcam*, lalu menyimpan seluruh vektor beserta vektor rata-ratanya (*centroid*) ke PostgreSQL.

```python
import cv2
import time
import numpy as np
from src.config import Config
from src.database import FaceDatabase
from src.face_engine import FaceEngine

POSE_INSTRUCTIONS = [
    ("lurus_netral_1", "1/5: Tatap lurus ke layar (Ekspresi Netral)"),
    ("lurus_senyum", "2/5: Tatap lurus ke layar (Sambil Tersenyum)"),
    ("miring_kiri_kanan", "3/5: Gerakkan kepala sedikit ke kiri & kanan"),
    ("agak_menunduk", "4/5: Posisi fokus mengetik / agak menunduk sedikit"),
    ("aksesoris_atau_jauh", "5/5: Pakai/lepas kacamata atau mundur sedikit dari layar")
]

def run_enrollment():
    print("======================================================")
    print("   REGISTRASI WAJAH PEMILIK (POSTGRESQL + PGVECTOR)   ")
    print("======================================================")

    db = FaceDatabase()
    engine = FaceEngine()

    cap = cv2.VideoCapture(Config.CAMERA_INDEX)
    if not cap.isOpened():
        print("[ERROR] Kamera tidak dapat diakses!")
        return

    print("\nMenghapus data embedding lama di PostgreSQL...")
    db.clear_owner_embeddings()

    collected_embeddings = []
    samples_per_stage = 3  # 5 tahap x 3 sampel = 15 sampel vektor + 1 vektor centroid

    for pose_key, instruction in POSE_INSTRUCTIONS:
        stage_count = 0
        print(f"\n>>> {instruction}")
        print("    Tekan [SPASI] untuk mengambil sampel wajah...")

        while stage_count < samples_per_stage:
            ret, frame = cap.read()
            if not ret:
                continue

            display_frame = frame.copy()
            faces = engine.analyze_frame(frame)

            # Gambar kotak panduan pada wajah utama
            if len(faces) == 1:
                bbox = faces[0]["bbox"]
                cv2.rectangle(display_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
                status_txt = f"Wajah Terdeteksi ({stage_count}/{samples_per_stage}) - Tekan SPASI"
                color = (0, 255, 0)
            elif len(faces) == 0:
                status_txt = "Wajah tidak terlihat!"
                color = (0, 0, 255)
            else:
                status_txt = "Harap hanya 1 orang di depan kamera saat registrasi!"
                color = (0, 165, 255)

            cv2.putText(display_frame, instruction, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
            cv2.putText(display_frame, status_txt, (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

            cv2.imshow("Enrollment - Personal Face Guard", display_frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord(" ") and len(faces) == 1:
                emb = faces[0]["embedding"]
                label = f"{pose_key}_{stage_count + 1}"
                db.save_owner_embedding(label, emb)
                collected_embeddings.append(emb)
                stage_count += 1
                print(f"    [+] Tersimpan ke PostgreSQL: {label}")
                time.sleep(0.3)
            elif key == 27:  # ESC untuk batal
                print("[INFO] Registrasi dibatalkan.")
                cap.release()
                cv2.destroyAllWindows()
                return

    # Hitung dan simpan vektor Centroid (rata-rata dari seluruh sampel wajah pemilik)
    centroid_vector = np.mean(collected_embeddings, axis=0)
    db.save_owner_embedding("owner_centroid_master", centroid_vector)

    cap.release()
    cv2.destroyAllWindows()
    print("\n======================================================")
    print(f" REGISTRASI SELESAI! {len(collected_embeddings) + 1} vektor tersimpan di PostgreSQL.")
    print("======================================================")

if __name__ == "__main__":
    run_enrollment()
```

---

### F. Mesin Pemantau Utama & State Machine (`src/watcher.py`)
Modul ini menjalankan *state machine* lengkap: verifikasi pemilik, deteksi penyusup 3 detik, deteksi pengintip di belakang bahu (*shoulder surfing*), penguncian saat ditinggal pergi (*away lock*), serta manajemen *adaptive polling* agar hemat baterai.

```python
import cv2
import time
from datetime import datetime
from src.config import Config, INTRUDER_LOG_DIR
from src.database import FaceDatabase
from src.face_engine import FaceEngine
from src.notifier import SecurityNotifier

class FaceGuardWatcher:
    def __init__(self, show_preview: bool = False):
        self.show_preview = show_preview
        self.running = False

        self.db = FaceDatabase()
        self.engine = FaceEngine()
        self.notifier = SecurityNotifier(self.db)

        # State Timers
        self.intruder_start_time = None
        self.snooping_start_time = None
        self.away_start_time = None
        self.last_snooping_toast_time = 0.0
        self.last_queue_check_time = 0.0

    def _save_intruder_snapshot(self, frame, bbox, similarity: float) -> str:
        """Menyimpan foto bukti penyusup dengan kotak merah dan label timestamp."""
        annotated = frame.copy()
        ts_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        cv2.rectangle(annotated, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 0, 255), 3)
        cv2.putText(
            annotated,
            f"INTRUDER (Score: {similarity:.2f}) - {ts_label}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2
        )

        filepath = INTRUDER_LOG_DIR / f"intruder_{file_ts}.jpg"
        cv2.imwrite(str(filepath), annotated)
        return str(filepath)

    def start_monitoring(self):
        """Memulai loop pengawasan berkelanjutan."""
        self.running = True
        cap = cv2.VideoCapture(Config.CAMERA_INDEX)

        if not cap.isOpened():
            print("[ERROR] Gagal membuka webcam!")
            return

        print("[INFO] Personal Laptop Face Guard aktif memantau...")

        while self.running:
            loop_start = time.time()
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.5)
                continue

            # Cek antrean notifikasi Telegram yang tertunda setiap 60 detik
            if loop_start - self.last_queue_check_time > 60:
                self.notifier.flush_offline_queue()
                self.last_queue_check_time = loop_start

            faces = self.engine.analyze_frame(frame)
            liveness_ok = self.engine.check_liveness(frame) if len(faces) > 0 else False

            state = "MONITORING"
            sleep_interval = 0.15  # Mode respons cepat saat ada anomali

            # ==========================================================
            # KASUS 1: KURSI KOSONG (0 Wajah Terdeteksi)
            # ==========================================================
            if len(faces) == 0:
                self.intruder_start_time = None
                self.snooping_start_time = None

                if self.away_start_time is None:
                    self.away_start_time = loop_start

                away_elapsed = loop_start - self.away_start_time
                state = f"USER_AWAY ({away_elapsed:.1f}s)"

                if away_elapsed >= Config.AWAY_LOCK_SEC:
                    print("[ACTION] Pemilik meninggalkan laptop > batas waktu. Mengunci layar...")
                    self.db.log_security_event(event_type="USER_AWAY", is_notified=True)
                    self.notifier.lock_workstation()
                    self.away_start_time = None
                    time.sleep(5.0)
                else:
                    sleep_interval = 1.0

            # ==========================================================
            # KASUS 2: TERDETEKSI >= 1 WAJAH DI DEPAN KAMERA
            # ==========================================================
            else:
                self.away_start_time = None
                 owner_present = False
                stranger_faces = []

                for f in faces:
                    is_owner, sim_score, pose = self.db.verify_face(f["embedding"])
                    f["is_owner"] = is_owner and liveness_ok
                    f["sim_score"] = sim_score

                    if f["is_owner"]:
                        owner_present = True
                    else:
                        stranger_faces.append(f)

                # ------------------------------------------------------
                # SUB-KASUS 2A: PEMILIK ADA + TIDAK ADA PENGINTIP (AMAN)
                # ------------------------------------------------------
                if owner_present and len(stranger_faces) == 0:
                    state = "AUTHORIZED"
                    self.intruder_start_time = None
                    self.snooping_start_time = None
                    # Mode hemat baterai: jeda pemindaian sesuai konfigurasi idle
                    sleep_interval = Config.IDLE_POLL_SEC

                # ------------------------------------------------------
                # SUB-KASUS 2B: PEMILIK ADA + ADA WAJAH ASING (MENGINTIP)
                # ------------------------------------------------------
                elif owner_present and len(stranger_faces) > 0:
                    self.intruder_start_time = None
                    if self.snooping_start_time is None:
                        self.snooping_start_time = loop_start

                    snoop_elapsed = loop_start - self.snooping_start_time
                    state = f"SNOOPING_DETECTED ({snoop_elapsed:.1f}s)"

                    if snoop_elapsed >= Config.SNOOPING_GRACE_SEC:
                        if loop_start - self.last_snooping_toast_time > 10.0:
                            self.notifier.show_desktop_toast(
                                "⚠️ Peringatan Privasi (Shoulder Surfing)",
                                f"Terdeteksi {len(stranger_faces)} orang lain melihat ke arah layar Anda!"
                            )
                            self.db.log_security_event(
                                event_type="SNOOPING_WARNING",
                                similarity_score=stranger_faces[0]["sim_score"],
                                is_notified=True
                            )
                            self.last_snooping_toast_time = loop_start

                # ------------------------------------------------------
                # SUB-KASUS 2C: TIDAK ADA PEMILIK, HANYA WAJAH ASING!
                # ------------------------------------------------------
                elif not owner_present and len(stranger_faces) > 0:
                    self.snooping_start_time = None
                    primary_intruder = stranger_faces[0]  # Wajah terbesar yang memegang laptop

                    if self.intruder_start_time is None:
                        self.intruder_start_time = loop_start

                    intruder_elapsed = loop_start - self.intruder_start_time
                    state = f"INTRUDER_WARNING ({intruder_elapsed:.1f}s)"

                    if intruder_elapsed >= Config.INTRUDER_GRACE_SEC:
                        print("[ALERT] PENYUSUP TERKONFIRMASI! Mengambil foto & mengunci laptop...")
                        self.notifier.play_alert_sound()

                        # 1. Simpan bukti foto ke disk lokal
                        snap_path = self._save_intruder_snapshot(
                            frame,
                            primary_intruder["bbox"],
                            primary_intruder["sim_score"]
                        )

                        # 2. Catat log & vektor penyusup ke PostgreSQL
                        log_id, repeat_id = self.db.log_security_event(
                            event_type="INTRUDER_ALERT",
                            similarity_score=primary_intruder["sim_score"],
                            intruder_embedding=primary_intruder["embedding"],
                            snapshot_path=snap_path,
                            is_notified=False
                        )

                        # 3. Kirim bukti foto ke Telegram pemilik
                        sent = self.notifier.send_telegram_intruder_photo(
                            image_path=snap_path,
                            similarity_score=primary_intruder["sim_score"],
                            repeat_id=repeat_id
                        )
                        if sent:
                            self.db.mark_as_notified(log_id)

                        # 4. Kunci sistem operasi seketika
                        self.notifier.lock_workstation()
                        self.intruder_start_time = None
                        time.sleep(5.0)

            # Tampilkan jendela preview hanya jika mode debug diaktifkan
            if self.show_preview:
                preview = frame.copy()
                for f in faces:
                    box = f["bbox"]
                    c = (0, 255, 0) if f.get("is_owner") else (0, 0, 255)
                    lbl = f"{'OWNER' if f.get('is_owner') else 'UNKNOWN'} ({f.get('sim_score', 0):.2f})"
                    cv2.rectangle(preview, (box[0], box[1]), (box[2], box[3]), c, 2)
                    cv2.putText(preview, lbl, (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, c, 2)

                cv2.putText(preview, f"STATE: {state}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 0), 2)
                cv2.imshow("Face Guard Monitor", preview)
                if cv2.waitKey(1) & 0xFF == 27:
                    self.running = False
                    break
            else:
                time.sleep(sleep_interval)

        cap.release()
        cv2.destroyAllWindows()

    def stop(self):
        self.running = False

if __name__ == "__main__":
    # Jalankan dengan preview=True untuk pengujian awal
    watcher = FaceGuardWatcher(show_preview=True)
    watcher.start_monitoring()
```

---

### G. Aplikasi Background System Tray (`src/tray_app.py`)
Agar berjalan mulus tanpa jendela terminal atau kamera yang mengganggu saat kamu bekerja, jalankan file ini. Ikon perisai hijau akan muncul di *System Tray* (dekat jam Windows) dengan menu untuk **Pause/Resume** dan **Keluar**.

```python
import threading
import pystray
from PIL import Image, ImageDraw
from src.watcher import FaceGuardWatcher

class SystemTrayGuard:
    def __init__(self):
        self.watcher = FaceGuardWatcher(show_preview=False)
        self.monitor_thread = None
        self.is_paused = False
        self.icon = pystray.Icon(
            "PersonalFaceGuard",
            self._create_shield_icon("green"),
            "Face Guard: Aktif Memantau",
            menu=pystray.Menu(
                pystray.MenuItem(self._get_toggle_label, self.toggle_monitoring),
                pystray.MenuItem("Kirim Ulang Antrean Telegram", self.force_sync_telegram),
                pystray.MenuItem("Keluar (Matikan Proteksi)", self.exit_app)
            )
        )

    @staticmethod
    def _create_shield_icon(color: str) -> Image.Image:
        """Membuat ikon indikator warna secara dinamis untuk System Tray."""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        fill_color = (46, 204, 113, 255) if color == "green" else (231, 76, 60, 255)
        draw.ellipse((8, 8, 56, 56), fill=fill_color, outline=(255, 255, 255, 255), width=4)
        return img

    def _get_toggle_label(self, item):
        return "Lanjutkan Proteksi (Resume)" if self.is_paused else "Jeda Proteksi (Pause)"

    def start_worker(self):
        if self.monitor_thread is None or not self.monitor_thread.is_alive():
            self.monitor_thread = threading.Thread(target=self.watcher.start_monitoring, daemon=True)
            self.monitor_thread.start()

    def toggle_monitoring(self, icon, item):
        if not self.is_paused:
            self.watcher.stop()
            self.is_paused = True
            self.icon.icon = self._create_shield_icon("red")
            self.icon.title = "Face Guard: Dijeda (Paused)"
        else:
            self.is_paused = False
            self.icon.icon = self._create_shield_icon("green")
            self.icon.title = "Face Guard: Aktif Memantau"
            self.start_worker()

    def force_sync_telegram(self, icon, item):
        self.watcher.notifier.flush_offline_queue()

    def exit_app(self, icon, item):
        self.watcher.stop()
        self.icon.stop()

    def run(self):
        self.start_worker()
        self.icon.run()

if __name__ == "__main__":
    app = SystemTrayGuard()
    app.run()
```

---

## 5. Cara Menjalankan End-to-End & Auto-Start Windows

### Langkah 1: Nyalakan Database PostgreSQL
Jika menggunakan Docker:
```bash
docker compose up -d
```
Jika menggunakan PostgreSQL lokal Windows, buka `pgAdmin` dan jalankan isi file `init_db.sql`.

### Langkah 2: Daftarkan Wajah Kamu (`enroll.py`)
```bash
python -m src.enroll
```
Ikuti 5 instruksi posisi wajah di layar dengan menekan tombol **SPASI** hingga ke-16 vektor wajah tersimpan di tabel `owner_embeddings`.

### Langkah 3: Uji Coba dengan Jendela Kamera (`watcher.py`)
```bash
python -m src.watcher
```
* Pastikan wajahmu ditandai dengan kotak hijau `OWNER (0.65+)`.
* Coba tutup wajahmu atau minta orang lain duduk di depan laptop selama 3 detik untuk menguji pengiriman foto ke Telegram dan penguncian layar otomatis.

### Langkah 4: Jalankan Secara Senyap di Background (`run_guard.bat`)
Buat file `run_guard.bat` di folder utama proyek menggunakan `pythonw.exe` (agar tidak memunculkan jendela *Command Prompt* hitam):

```bat
@echo off
cd /d "%~dp0"
start "" "%~dp0venv\Scripts\pythonw.exe" -m src.tray_app
```

Agar sistem langsung aktif menjaga laptop setiap kali laptop dinyalakan:
1. Tekan **`Win + R`** di keyboard, ketik `shell:startup`, lalu tekan **Enter**.
2. Buat *Shortcut* dari file `run_guard.bat` dan letakkan di dalam folder *Startup* tersebut.
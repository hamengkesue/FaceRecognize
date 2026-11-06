import logging
import platform
import time
import cv2
import numpy as np

from src.config import Config
from src.database import FaceDatabase
from src.face_engine import FaceEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FaceGuard.Enroll")

POSE_INSTRUCTIONS = [
    ("lurus_netral", "1/5: Tatap lurus ke layar (Ekspresi Netral)"),
    ("lurus_senyum", "2/5: Tatap lurus ke layar (Sambil Tersenyum)"),
    ("miring_kiri_kanan", "3/5: Gerakkan kepala sedikit ke kiri & kanan"),
    ("agak_menunduk", "4/5: Posisi fokus mengetik / agak menunduk sedikit"),
    ("aksesoris_atau_jauh", "5/5: Pakai/lepas kacamata atau mundur sedikit dari layar")
]


def open_webcam(camera_index: int):
    """Opens webcam using DirectShow on Windows for instant startup."""
    if platform.system() == "Windows":
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(camera_index)
    return cap


def run_enrollment():
    print("=" * 60)
    print("      REGISTRASI WAJAH PEMILIK (PERSONAL FACE GUARD)      ")
    print("=" * 60)

    db = FaceDatabase()
    engine = FaceEngine()

    cap = open_webcam(Config.CAMERA_INDEX)
    if not cap.isOpened():
        print(f"[ERROR] Kamera (index {Config.CAMERA_INDEX}) tidak dapat diakses!")
        return

    print("\nMenghapus data embedding lama di PostgreSQL...")
    db.clear_owner_embeddings()

    collected_embeddings = []
    samples_per_stage = 3  # 5 tahap x 3 sampel = 15 sampel vektor + 1 vektor centroid

    for pose_key, instruction in POSE_INSTRUCTIONS:
        stage_count = 0
        print(f"\n>>> {instruction}")
        print("    Tekan [SPASI] untuk mengambil sampel wajah (ESC untuk batal)...")

        while stage_count < samples_per_stage:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            display_frame = frame.copy()
            faces = engine.analyze_frame(frame)

            # Guide user with color-coded feedback
            if len(faces) == 1:
                bbox = faces[0]["bbox"]
                cv2.rectangle(display_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
                status_txt = f"Wajah Siap ({stage_count}/{samples_per_stage}) - Tekan [SPASI]"
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
                print(f"    [+] Sampel tersimpan ({stage_count}/{samples_per_stage}): {label}")
                time.sleep(0.3)
            elif key == 27:  # ESC to cancel
                print("[INFO] Registrasi dibatalkan oleh pengguna.")
                cap.release()
                cv2.destroyAllWindows()
                return

    # Calculate and save Centroid Vector (master average of all owner face samples)
    if collected_embeddings:
        centroid_vector = np.mean(collected_embeddings, axis=0)
        norm_centroid = centroid_vector / np.linalg.norm(centroid_vector)
        db.save_owner_embedding("owner_centroid_master", norm_centroid)

    # Refresh in-memory cache
    db.reload_cache()

    cap.release()
    cv2.destroyAllWindows()
    print("\n" + "=" * 60)
    print(f" REGISTRASI SELESAI! {len(collected_embeddings) + 1} vektor berhasil tersimpan.")
    print(" Sistem siap menjalankan pemantauan (watcher.py).")
    print("=" * 60)


if __name__ == "__main__":
    run_enrollment()


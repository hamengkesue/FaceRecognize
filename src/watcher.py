import logging
import platform
import time
from datetime import datetime
from typing import Optional
import cv2

from src.config import Config, INTRUDER_LOG_DIR
from src.database import FaceDatabase
from src.face_engine import FaceEngine
from src.notifier import SecurityNotifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FaceGuard.Watcher")


class FaceGuardWatcher:
    def __init__(self, show_preview: bool = False):
        self.show_preview = show_preview
        self.running = False

        self.db = FaceDatabase()
        self.engine = FaceEngine()
        self.notifier = SecurityNotifier(self.db)

        # State machine timers
        self.intruder_start_time: Optional[float] = None
        self.snooping_start_time: Optional[float] = None
        self.away_start_time: Optional[float] = None
        self.last_snooping_toast_time: float = 0.0
        self.last_queue_check_time: float = 0.0

    def _open_camera(self):
        """Initializes camera using DirectShow on Windows for fast capture startup."""
        if platform.system() == "Windows":
            return cv2.VideoCapture(Config.CAMERA_INDEX, cv2.CAP_DSHOW)
        return cv2.VideoCapture(Config.CAMERA_INDEX)

    def _save_intruder_snapshot(self, frame, bbox, similarity: float) -> str:
        """Annotates and saves intruder evidence snapshot to local storage."""
        annotated = frame.copy()
        ts_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        cv2.rectangle(annotated, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 0, 255), 3)
        cv2.putText(
            annotated,
            f"INTRUDER (Sim: {similarity:.2f}) - {ts_label}",
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
        """Main continuous facial verification monitoring loop."""
        self.running = True
        cap = self._open_camera()

        if not cap.isOpened():
            logger.error("Could not open webcam index %s!", Config.CAMERA_INDEX)
            self.running = False
            return

        logger.info("Personal Laptop Face Guard active. Monitoring workstation security...")

        while self.running:
            loop_start = time.time()
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            # Flush offline Telegram notifications every 60 seconds
            if loop_start - self.last_queue_check_time > 60.0:
                self.notifier.flush_offline_queue()
                self.last_queue_check_time = loop_start

            faces = self.engine.analyze_frame(frame)

            state = "MONITORING"
            sleep_interval = 0.15  # Fast loop rate when anomaly suspected

            # ==========================================================
            # CASE 1: EMPTY CHAIR (0 Faces Detected)
            # ==========================================================
            if len(faces) == 0:
                self.intruder_start_time = None
                self.snooping_start_time = None

                if self.away_start_time is None:
                    self.away_start_time = loop_start

                away_elapsed = loop_start - self.away_start_time
                state = f"USER_AWAY ({away_elapsed:.1f}s)"

                if away_elapsed >= Config.AWAY_LOCK_SEC:
                    logger.warning("[AWAY] Owner left workstation for %.1fs. Locking workstation...", away_elapsed)
                    self.db.log_security_event(event_type="USER_AWAY", is_notified=True)
                    self.notifier.lock_workstation()
                    self.away_start_time = None
                    time.sleep(5.0)
                else:
                    sleep_interval = 1.0

            # ==========================================================
            # CASE 2: AT LEAST 1 FACE DETECTED
            # ==========================================================
            else:
                self.away_start_time = None
                owner_present = False
                stranger_faces = []

                for f in faces:
                    is_owner_match, sim_score, pose = self.db.verify_face(f["embedding"], use_cache=True)
                    liveness_ok = self.engine.check_liveness(frame, target_bbox=f["bbox"], face_data=f)

                    # Owner must pass both embedding similarity and liveness
                    f["is_owner"] = is_owner_match and liveness_ok
                    f["sim_score"] = sim_score
                    f["matched_pose"] = pose

                    if f["is_owner"]:
                        owner_present = True
                    else:
                        stranger_faces.append(f)

                # ------------------------------------------------------
                # SUB-CASE 2A: OWNER PRESENT & NO SNOOPERS (AUTHORIZED)
                # ------------------------------------------------------
                if owner_present and len(stranger_faces) == 0:
                    state = "AUTHORIZED"
                    self.intruder_start_time = None
                    self.snooping_start_time = None
                    # Adaptive Duty-Cycle: lower CPU usage when safe (PRD 4.4)
                    sleep_interval = Config.IDLE_POLL_SEC

                # ------------------------------------------------------
                # SUB-CASE 2B: OWNER PRESENT + SNOOPERS (SHOULDER SURFING)
                # ------------------------------------------------------
                elif owner_present and len(stranger_faces) > 0:
                    self.intruder_start_time = None
                    if self.snooping_start_time is None:
                        self.snooping_start_time = loop_start

                    snoop_elapsed = loop_start - self.snooping_start_time
                    state = f"SNOOPING_DETECTED ({snoop_elapsed:.1f}s)"

                    if snoop_elapsed >= Config.SNOOPING_GRACE_SEC:
                        if loop_start - self.last_snooping_toast_time > 10.0:
                            logger.warning("[SNOOPING] Shoulder surfing detected: %d strangers behind owner.", len(stranger_faces))
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
                # SUB-CASE 2C: NO OWNER, ONLY STRANGER(S) (INTRUDER)
                # ------------------------------------------------------
                elif not owner_present and len(stranger_faces) > 0:
                    self.snooping_start_time = None
                    primary_intruder = stranger_faces[0]  # Largest face operating laptop

                    if self.intruder_start_time is None:
                        self.intruder_start_time = loop_start

                    intruder_elapsed = loop_start - self.intruder_start_time
                    state = f"INTRUDER_WARNING ({intruder_elapsed:.1f}s)"

                    if intruder_elapsed >= Config.INTRUDER_GRACE_SEC:
                        logger.critical("[INTRUDER] Unauthorized user confirmed for %.1fs! Triggering defense...", intruder_elapsed)
                        self.notifier.play_alert_sound()

                        # 1. Capture evidence snapshot
                        snap_path = self._save_intruder_snapshot(
                            frame,
                            primary_intruder["bbox"],
                            primary_intruder["sim_score"]
                        )

                        # 2. Record security log in PostgreSQL
                        log_id, repeat_id = self.db.log_security_event(
                            event_type="INTRUDER_ALERT",
                            similarity_score=primary_intruder["sim_score"],
                            intruder_embedding=primary_intruder["embedding"],
                            snapshot_path=snap_path,
                            is_notified=False
                        )

                        # 3. Send photo via Telegram
                        sent = self.notifier.send_telegram_intruder_photo(
                            image_path=snap_path,
                            similarity_score=primary_intruder["sim_score"],
                            repeat_id=repeat_id
                        )
                        if sent and log_id is not None:
                            self.db.mark_as_notified(log_id)

                        # 4. Lock operating system instantly
                        self.notifier.lock_workstation()
                        self.intruder_start_time = None
                        time.sleep(5.0)

            # Debug Preview Window
            if self.show_preview:
                preview = frame.copy()
                for f in faces:
                    box = f["bbox"]
                    is_own = f.get("is_owner", False)
                    c = (0, 255, 0) if is_own else (0, 0, 255)
                    tag = "OWNER" if is_own else "UNKNOWN"
                    score = f.get("sim_score", 0.0)
                    lbl = f"{tag} ({score:.2f})"
                    cv2.rectangle(preview, (box[0], box[1]), (box[2], box[3]), c, 2)
                    cv2.putText(preview, lbl, (box[0], max(20, box[1] - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, c, 2)

                cv2.putText(preview, f"STATE: {state}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 0), 2)
                cv2.imshow("Face Guard Monitor", preview)
                key = cv2.waitKey(1) & 0xFF
                if key == 27:  # ESC to stop
                    self.running = False
                    break
            else:
                time.sleep(sleep_interval)

        cap.release()
        cv2.destroyAllWindows()
        logger.info("Face Guard Watcher stopped.")

    def stop(self):
        """Stops the monitoring loop gracefully."""
        self.running = False


if __name__ == "__main__":
    watcher = FaceGuardWatcher(show_preview=True)
    watcher.start_monitoring()


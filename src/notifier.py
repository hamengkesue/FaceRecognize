import ctypes
import logging
import os
import platform
import sys
from datetime import datetime
from typing import Optional
from plyer import notification
import requests

from src.config import Config
from src.database import FaceDatabase

logger = logging.getLogger("FaceGuard.Notifier")


class SecurityNotifier:
    def __init__(self, db: FaceDatabase):
        self.db = db

    @staticmethod
    def play_alert_sound():
        """Plays alert sound or custom .wav to deter unauthorized user."""
        if not Config.ENABLE_AUDIO_ALERT:
            return

        os_name = platform.system()
        try:
            if os_name == "Windows":
                import winsound
                if Config.CUSTOM_ALERT_SOUND.is_file():
                    winsound.PlaySound(
                        str(Config.CUSTOM_ALERT_SOUND),
                        winsound.SND_FILENAME | winsound.SND_ASYNC
                    )
                else:
                    winsound.Beep(1800, 350)
                    winsound.Beep(2200, 450)
            else:
                sys.stdout.write("\a")
                sys.stdout.flush()
        except Exception as e:
            logger.warning("Failed to play alert sound: %s", e)

    @staticmethod
    def show_desktop_toast(title: str, message: str):
        """Displays native desktop notification toast."""
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="Laptop Face Guard",
                timeout=4
            )
        except Exception as e:
            logger.warning("Failed to display desktop toast: %s", e)

    @staticmethod
    def lock_workstation():
        """Immediately locks the operating system session."""
        os_name = platform.system()
        logger.info("Executing LockWorkStation on OS: %s", os_name)
        try:
            if os_name == "Windows":
                ctypes.windll.user32.LockWorkStation()
            elif os_name == "Darwin":  # macOS
                os.system("/System/Library/CoreServices/Menu\\ Extras/User.menu/Contents/Resources/CGSession -suspend")
            elif os_name == "Linux":
                os.system("xdg-screensaver lock 2>/dev/null || loginctl lock-session 2>/dev/null")
        except Exception as e:
            logger.error("Failed to lock workstation: %s", e)

    def send_telegram_intruder_photo(
        self,
        image_path: str,
        similarity_score: float,
        repeat_id: Optional[int] = None,
        timestamp_str: Optional[str] = None
    ) -> bool:
        """Sends intruder photo and incident details to owner via Telegram Bot API."""
        if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
            logger.debug("Telegram credentials not configured; skipping Telegram photo push.")
            return False

        if not os.path.isfile(image_path):
            logger.warning("Snapshot file not found: %s", image_path)
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
            if response.status_code == 200:
                logger.info("Telegram photo alert delivered successfully.")
                return True
            else:
                logger.warning("Telegram API error (%s): %s", response.status_code, response.text)
                return False
        except Exception as e:
            logger.info("Telegram push failed (offline): %s. Will retry when reconnected.", e)
            return False

    def flush_offline_queue(self):
        """Flushes pending intruder photos from local database once internet is restored."""
        pending_logs = self.db.get_pending_notifications()
        if not pending_logs:
            return

        logger.info("Checking offline queue: %d alerts pending delivery...", len(pending_logs))
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
                    logger.info("Successfully flushed queued alert for Log #%s", log["id"])


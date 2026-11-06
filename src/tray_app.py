import logging
import threading
import time
from PIL import Image, ImageDraw
import pystray

from src.watcher import FaceGuardWatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FaceGuard.TrayApp")


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
        """Dynamically draws a crisp shield icon for the Windows taskbar tray."""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        fill_color = (46, 204, 113, 255) if color == "green" else (231, 76, 60, 255)

        # Draw outer circle and border
        draw.ellipse((6, 6, 58, 58), fill=fill_color, outline=(255, 255, 255, 255), width=4)

        # Draw inner accent (small dot or star)
        draw.ellipse((26, 26, 38, 38), fill=(255, 255, 255, 230))
        return img

    def _get_toggle_label(self, item):
        return "Lanjutkan Proteksi (Resume)" if self.is_paused else "Jeda Proteksi (Pause)"

    def start_worker(self):
        """Starts background watcher thread safely."""
        if self.monitor_thread is None or not self.monitor_thread.is_alive():
            self.watcher = FaceGuardWatcher(show_preview=False)
            self.monitor_thread = threading.Thread(target=self.watcher.start_monitoring, daemon=True)
            self.monitor_thread.start()
            logger.info("Watcher thread started in background.")

    def toggle_monitoring(self, icon, item):
        if not self.is_paused:
            logger.info("Pausing Face Guard protection...")
            self.watcher.stop()
            self.is_paused = True
            self.icon.icon = self._create_shield_icon("red")
            self.icon.title = "Face Guard: Dijeda (Paused)"
        else:
            logger.info("Resuming Face Guard protection...")
            self.is_paused = False
            self.icon.icon = self._create_shield_icon("green")
            self.icon.title = "Face Guard: Aktif Memantau"
            self.start_worker()

    def force_sync_telegram(self, icon, item):
        logger.info("Manually triggering pending Telegram alerts flush...")
        threading.Thread(target=self.watcher.notifier.flush_offline_queue, daemon=True).start()

    def exit_app(self, icon, item):
        logger.info("Exiting Face Guard System Tray...")
        self.watcher.stop()
        self.icon.stop()

    def run(self):
        self.start_worker()
        logger.info("Starting System Tray Icon loop...")
        self.icon.run()


if __name__ == "__main__":
    app = SystemTrayGuard()
    app.run()


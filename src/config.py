import os
from pathlib import Path
from dotenv import load_dotenv

# Root project directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / ".env")

# Evidence snapshot directory
INTRUDER_LOG_DIR = BASE_DIR / "logs" / "intruders"
INTRUDER_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Assets directories
ASSETS_DIR = BASE_DIR / "assets"
SOUNDS_DIR = ASSETS_DIR / "sounds"
SOUNDS_DIR.mkdir(parents=True, exist_ok=True)


class Config:
    # PostgreSQL Configuration
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "face_guard_db")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "password_rahasia")

    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    # Camera & Detection Settings
    CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.50"))

    # State Machine Durations (in seconds)
    INTRUDER_GRACE_SEC: float = float(os.getenv("INTRUDER_GRACE_SEC", "3.0"))
    SNOOPING_GRACE_SEC: float = float(os.getenv("SNOOPING_GRACE_SEC", "2.0"))
    AWAY_LOCK_SEC: float = float(os.getenv("AWAY_LOCK_SEC", "30.0"))
    IDLE_POLL_SEC: float = float(os.getenv("IDLE_POLL_SEC", "2.5"))

    # Security & Alert Features
    LIVENESS_ENABLED: bool = os.getenv("LIVENESS_ENABLED", "true").lower() in ("true", "1", "yes")
    ENABLE_AUDIO_ALERT: bool = os.getenv("ENABLE_AUDIO_ALERT", "true").lower() in ("true", "1", "yes")

    # Custom Alert Sound file (optional)
    CUSTOM_ALERT_SOUND: Path = SOUNDS_DIR / "alert.wav"


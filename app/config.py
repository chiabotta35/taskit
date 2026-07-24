import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{DATA_DIR / 'taskit.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() in ("true", "1", "yes")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB upload limit
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")

    @staticmethod
    def init_app(app):
        key = app.config.get("SECRET_KEY", "")
        defaults = {"dev-secret-change-me", "change-me-in-production", "changeme", ""}
        if key in defaults:
            logger.warning(
                "SECRET_KEY is set to a default/insecure value. "
                "Set a strong random SECRET_KEY in your environment or .env file. "
                "Session cookies CAN BE FORGED with the default key."
            )

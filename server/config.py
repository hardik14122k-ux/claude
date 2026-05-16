"""Central configuration. All environment-specific values live here."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ---- Database ----
DB_PATH: Path = Path(os.environ.get("HRMS_DB_PATH", str(BASE_DIR / "data.db")))

# ---- Flask ----
SECRET_KEY: str = os.environ.get("HRMS_SECRET_KEY", "dev-secret-change-me-in-production")
MAX_UPLOAD_BYTES: int = int(os.environ.get("HRMS_MAX_UPLOAD_MB", "10")) * 1024 * 1024

# ---- Multi-tenancy ----
DEFAULT_TENANT: str = "default"

# ---- Auth ----
SESSION_LIFETIME_HOURS: int = int(os.environ.get("HRMS_SESSION_HOURS", "8"))
BCRYPT_ROUNDS: int = int(os.environ.get("HRMS_BCRYPT_ROUNDS", "12"))

# ---- Notifications (stubs — override with real values) ----
SMTP_HOST: str = os.environ.get("SMTP_HOST", "")
SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER: str = os.environ.get("SMTP_USER", "")
SMTP_PASS: str = os.environ.get("SMTP_PASS", "")
SMTP_FROM: str = os.environ.get("SMTP_FROM", "hrms@example.com")

SLACK_WEBHOOK: str = os.environ.get("SLACK_WEBHOOK", "")
WHATSAPP_API_KEY: str = os.environ.get("WHATSAPP_API_KEY", "")
SMS_API_KEY: str = os.environ.get("SMS_API_KEY", "")

# ---- File Storage ----
UPLOAD_DIR: Path = Path(os.environ.get("HRMS_UPLOAD_DIR", str(BASE_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

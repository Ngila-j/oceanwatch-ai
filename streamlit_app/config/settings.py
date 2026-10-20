"""Streamlit app configuration (env / secrets overridable)."""
from __future__ import annotations
import os
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from db_config import get_db_uri

def get_settings_db_uri() -> str:
    return get_db_uri()

# Prefer get_db_uri() at engine creation; this is a snapshot for simple imports
DB_URI = get_db_uri()

APP_NAME = "OceanWatch AI"
DEFAULT_TZ = "Africa/Nairobi"
PAGE_SIZE = 500
EVENT_BUS_CACHE_TTL_SEC = 45
DEMO_MODE = os.getenv("OCEANWATCH_DEMO_MODE", "").lower() in {"1", "true", "yes"}

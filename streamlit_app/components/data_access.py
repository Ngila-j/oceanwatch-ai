import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

DB_URI = os.getenv(
    "OCEANWATCH_DB_URI",
    "postgresql://postgres:password@localhost:5433/oceanwatch_db",
)


def get_engine():
    return create_engine(DB_URI, pool_pre_ping=True)


def qdf(sql: str) -> pd.DataFrame:
    try:
        return pd.read_sql(text(sql), get_engine())
    except Exception:
        return pd.DataFrame()


def load_status_strip() -> dict:
    """Latest timestamps for Home status strip."""
    out = {
        "ocean": None,
        "wio": None,
        "quality": None,
        "port": None,
        "alerts_n": 0,
    }
    try:
        eng = get_engine()
        out["ocean"] = pd.read_sql(
            text("SELECT MAX(date_key) AS t FROM fact_ocean_conditions"), eng
        ).iloc[0]["t"]
        out["wio"] = pd.read_sql(
            text("SELECT MAX(index_date) AS t FROM fact_wio_intelligence_index"), eng
        ).iloc[0]["t"]
        out["quality"] = pd.read_sql(
            text("SELECT MAX(scored_at) AS t FROM fact_data_quality"), eng
        ).iloc[0]["t"]
        out["port"] = pd.read_sql(
            text("SELECT MAX(metric_date) AS t FROM fact_port_metrics"), eng
        ).iloc[0]["t"]
        out["alerts_n"] = int(
            pd.read_sql(text("SELECT COUNT(*) AS n FROM fact_alerts"), eng).iloc[0]["n"]
        )
    except Exception:
        pass
    return out


def reports_dir() -> Path:
    # Host project reports/ (sibling of streamlit_app)
    return Path(__file__).resolve().parents[2] / "reports"


def list_briefs():
    d = reports_dir()
    if not d.exists():
        return []
    return sorted(d.glob("weekly_ocean_brief_*.pdf"), reverse=True)
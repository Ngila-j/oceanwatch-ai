"""Shared SQLAlchemy helpers for Streamlit pages."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_DEFAULT_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"

DB_URI = os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or _DEFAULT_URI


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Process-level engine (pool_pre_ping for stale connections)."""
    return create_engine(DB_URI, pool_pre_ping=True)


def qdf(sql: str, params: Optional[dict[str, Any]] = None) -> pd.DataFrame:
    """Run SQL and return a DataFrame; empty frame on failure."""
    try:
        with get_engine().connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})
    except Exception:
        return pd.DataFrame()


def qdf_or_error(sql: str, params: Optional[dict[str, Any]] = None) -> pd.DataFrame:
    """
    Like qdf, but surfaces the error message in an `error` column so UIs
    can distinguish "empty" from "broken schema / down DB".
    """
    try:
        with get_engine().connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})
    except Exception as exc:
        return pd.DataFrame({"error": [str(exc)]})


def has_error(df: Optional[pd.DataFrame]) -> bool:
    return df is not None and not df.empty and "error" in df.columns


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
        with eng.connect() as conn:
            out["ocean"] = pd.read_sql(
                text("SELECT MAX(date_key) AS t FROM fact_ocean_conditions"), conn
            ).iloc[0]["t"]
            out["wio"] = pd.read_sql(
                text("SELECT MAX(as_of_date) AS t FROM fact_wio_intelligence_index"),
                conn,
            ).iloc[0]["t"]
            out["quality"] = pd.read_sql(
                text("SELECT MAX(scored_at) AS t FROM fact_data_quality"), conn
            ).iloc[0]["t"]
            out["port"] = pd.read_sql(
                text("SELECT MAX(metric_date) AS t FROM fact_port_metrics"), conn
            ).iloc[0]["t"]
            out["alerts_n"] = int(
                pd.read_sql(
                    text("SELECT COUNT(*) AS n FROM fact_alerts"), conn
                ).iloc[0]["n"]
            )
    except Exception:
        pass
    return out


def reports_dir() -> Path:
    # Host project reports/ (sibling of streamlit_app)
    return Path(__file__).resolve().parents[2] / "reports"


def latest_weekly_briefs(limit: int = 5) -> list[Path]:
    d = reports_dir()
    if not d.exists():
        return []
    return sorted(d.glob("weekly_ocean_brief_*.pdf"), reverse=True)[:limit]


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------

def load_event_bus_bundle(limit: int = 500) -> dict[str, pd.DataFrame]:
    """Topics, consumers, recent events, and status aggregates for the UI."""
    lim = max(1, min(int(limit), 5000))

    # Prefer full projection; fall back if source_key not migrated yet
    events = qdf_or_error(
        f"""
        SELECT
            event_id, topic, event_type, severity, status,
            region_id, country_id, source_table, source_key,
            created_at, processed_at, model_version, payload
        FROM event_bus
        ORDER BY created_at DESC
        LIMIT {lim}
        """
    )
    if has_error(events):
        events = qdf_or_error(
            f"""
            SELECT
                event_id, topic, event_type, severity, status,
                region_id, country_id, source_table,
                created_at, processed_at, model_version, payload
            FROM event_bus
            ORDER BY created_at DESC
            LIMIT {lim}
            """
        )

    return {
        "topics": qdf_or_error(
            "SELECT topic, description, status FROM event_bus_topics ORDER BY topic"
        ),
        "consumers": qdf_or_error(
            """
            SELECT consumer_id, consumer_name, topics, status, last_seen_at
            FROM event_bus_consumers
            ORDER BY consumer_id
            """
        ),
        "events": events,
        "stats": qdf_or_error(
            """
            SELECT
                COUNT(*)::bigint AS total_events,
                SUM(
                    CASE WHEN UPPER(COALESCE(status, 'PENDING')) = 'PENDING' THEN 1 ELSE 0 END
                )::bigint AS pending,
                SUM(
                    CASE WHEN UPPER(COALESCE(status, '')) = 'PROCESSED' THEN 1 ELSE 0 END
                )::bigint AS processed,
                COUNT(DISTINCT topic)::bigint AS topic_n,
                MAX(created_at) AS latest_at
            FROM event_bus
            """
        ),
        "by_topic": qdf_or_error(
            """
            SELECT
                topic,
                COUNT(*)::bigint AS n,
                SUM(
                    CASE WHEN UPPER(COALESCE(status, 'PENDING')) = 'PENDING' THEN 1 ELSE 0 END
                )::bigint AS pending_n,
                MAX(created_at) AS latest_at
            FROM event_bus
            GROUP BY topic
            ORDER BY n DESC
            """
        ),
        "by_severity": qdf_or_error(
            """
            SELECT
                UPPER(COALESCE(severity, 'INFO')) AS severity,
                COUNT(*)::bigint AS n
            FROM event_bus
            GROUP BY 1
            ORDER BY n DESC
            """
        ),
    }

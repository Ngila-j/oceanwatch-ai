"""
Seed minimal demo rows so Streamlit Cloud pages render after schema init.

Safe to re-run: clears demo rows by fixed IDs / recent metric_date then inserts.
Uses ingestion/.env OCEANWATCH_DB_URI (Supabase).
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_dotenv() -> None:
    if not _ENV_FILE.exists():
        return
    for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_db_uri() -> str:
    _load_dotenv()
    uri = (os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or "").strip()
    if not uri:
        raise SystemExit("Set OCEANWATCH_DB_URI in ingestion/.env")
    return uri.replace("postgresql+psycopg2://", "postgresql://")


def seed() -> None:
    uri = get_db_uri()
    safe = uri.split("@")[-1] if "@" in uri else uri
    logger.info("Seeding demo data → ...@%s", safe)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today = date.today()
    d0 = today.isoformat()
    d1 = (today - timedelta(days=1)).isoformat()

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{uri}' AS pg (TYPE POSTGRES);")

    # Alerts
    con.execute("DELETE FROM pg.public.fact_alerts WHERE alert_id BETWEEN 9001 AND 9010;")
    con.execute(
        f"""
        INSERT INTO pg.public.fact_alerts VALUES
        (9001, 'SST_ANOMALY', 'COASTAL', 'ELEVATED',
         TIMESTAMP '{now.isoformat(sep=" ")}', TIMESTAMP '{now.isoformat(sep=" ")}',
         'Kenya EEZ · NE sector', NULL, 82.0, 71.0,
         'SST warm anomaly near Lamu corridor',
         '7-day SST mean above 30d baseline in monitoring box.',
         'mean_7d=+0.9C vs 30d; source=demo',
         'OPEN', NULL),
        (9002, 'PORT_CONGESTION', 'PORT', 'WATCH',
         TIMESTAMP '{now.isoformat(sep=" ")}', TIMESTAMP '{now.isoformat(sep=" ")}',
         'Port of Mombasa', NULL, 75.0, 58.0,
         'Mombasa waiting time elevated',
         'Average anchorage wait above moderate threshold.',
         'avg_waiting_hours=18; congestion_index=62; source=demo',
         'OPEN', NULL),
        (9003, 'FISHING_RISK', 'FISHING', 'CRITICAL',
         TIMESTAMP '{now.isoformat(sep=" ")}', TIMESTAMP '{now.isoformat(sep=" ")}',
         'EEZ outer box', 'FV DEMO-1', 88.0, 84.0,
         'Dark-activity pattern near EEZ edge',
         'AIS gap + loitering signature (demo seed).',
         'gap_hours=14; loiter=true; source=demo',
         'OPEN', NULL);
        """
    )

    # Ocean anomalies
    con.execute("DELETE FROM pg.public.fact_ocean_anomalies WHERE anomaly_id BETWEEN 9001 AND 9010;")
    con.execute(
        f"""
        INSERT INTO pg.public.fact_ocean_anomalies VALUES
        (9001, DATE '{d0}', 'SST', 28.4, 27.6, 27.1, 0.8, 2.9, 'ELEVATED',
         TIMESTAMP '{now.isoformat(sep=" ")}'),
        (9002, DATE '{d0}', 'CHL', 0.42, 0.31, 0.28, 0.11, 35.5, 'WATCH',
         TIMESTAMP '{now.isoformat(sep=" ")}');
        """
    )

    # Port metrics
    con.execute(
        f"DELETE FROM pg.public.fact_port_metrics WHERE port_name = 'Mombasa' AND metric_date IN (DATE '{d0}', DATE '{d1}');"
    )
    con.execute(
        f"""
        INSERT INTO pg.public.fact_port_metrics VALUES
        (DATE '{d0}', 'Mombasa', 14, 11, 42, 18, 6, 9, 18.5, 62.0, 'MODERATE', 12.0,
         TIMESTAMP '{now.isoformat(sep=" ")}'),
        (DATE '{d1}', 'Mombasa', 12, 13, 38, 16, 5, 8, 14.0, 48.0, 'LOW', 3.0,
         TIMESTAMP '{now.isoformat(sep=" ")}');
        """
    )

    # Fishing risk
    con.execute("DELETE FROM pg.public.fact_fishing_risk WHERE risk_id BETWEEN 9001 AND 9010;")
    con.execute(
        f"""
        INSERT INTO pg.public.fact_fishing_risk VALUES
        (9001, TIMESTAMP '{now.isoformat(sep=" ")}', 'FV DEMO-1', 'fishing', 'UNK',
         -2.15, 41.8, 84.0, 88.0, 'demo AIS gap', 'OPEN',
         TIMESTAMP '{now.isoformat(sep=" ")}');
        """
    )

    con.close()
    logger.info("Demo seed complete (alerts/anomalies/port/fishing).")


if __name__ == "__main__":
    seed()

"""
Create + seed fact_wio_intelligence_index for Streamlit WIO page.

Columns match compute_wio_index.py / pages/18_WIO_Intelligence_Index.py.
Uses ingestion/.env OCEANWATCH_DB_URI. Safe to re-run.
"""

from __future__ import annotations

import logging
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_ENV = Path(__file__).resolve().parent / ".env"


def _load_dotenv() -> None:
    if not _ENV.exists():
        return
    for raw in _ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_uri() -> str:
    _load_dotenv()
    uri = (os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or "").strip()
    if not uri:
        raise SystemExit("Set OCEANWATCH_DB_URI in ingestion/.env")
    return uri.replace("postgresql+psycopg2://", "postgresql://")


def main() -> None:
    uri = get_uri()
    safe = uri.split("@")[-1] if "@" in uri else uri
    logger.info("WIO index → ...@%s", safe)

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{uri}' AS pg (TYPE POSTGRES);")

    # Drop legacy narrow schema if present (phase9 names differ from app)
    # Prefer additive create matching app columns.
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_wio_intelligence_index (
            index_date DATE NOT NULL,
            region_id VARCHAR NOT NULL,
            ocean_health_score DOUBLE,
            maritime_activity_score DOUBLE,
            fishing_pressure_score DOUBLE,
            port_risk_score DOUBLE,
            environmental_risk_score DOUBLE,
            overall_score DOUBLE,
            confidence_score DOUBLE,
            drivers VARCHAR,
            methodology_version VARCHAR,
            created_at TIMESTAMP
        );
        """
    )

    today = date.today()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    region = "kenya_eez"

    # Clear demo window then insert ~21 days
    start = today - timedelta(days=21)
    con.execute(
        f"""
        DELETE FROM pg.public.fact_wio_intelligence_index
        WHERE region_id = '{region}'
          AND index_date >= DATE '{start.isoformat()}'
          AND methodology_version IN ('v1.0', 'v1.0-demo');
        """
    )

    # Pull live signals if available
    sst = None
    cong = None
    try:
        row = con.execute(
            """
            SELECT AVG(sst_celsius) FROM (
                SELECT sst_celsius FROM pg.public.fact_ocean_conditions
                WHERE sst_celsius IS NOT NULL
                ORDER BY date_key DESC LIMIT 14
            ) s
            """
        ).fetchone()
        sst = float(row[0]) if row and row[0] is not None else None
    except Exception:
        pass
    try:
        row = con.execute(
            """
            SELECT congestion_index FROM pg.public.fact_port_metrics
            ORDER BY metric_date DESC LIMIT 1
            """
        ).fetchone()
        cong = float(row[0]) if row and row[0] is not None else None
    except Exception:
        pass

    base_ocean = 70.0
    if sst is not None:
        base_ocean = max(0.0, min(100.0, 100 - abs(sst - 26.5) * 15))
    base_port_risk = cong if cong is not None else 55.0
    base_maritime = 58.0
    base_fish = 42.0
    base_env = 28.0

    rows_sql = []
    for i in range(20, -1, -1):
        d = today - timedelta(days=i)
        wave = math.sin(i / 3.5) * 4.0
        ocean = max(0.0, min(100.0, base_ocean + wave))
        maritime = max(0.0, min(100.0, base_maritime + wave * 0.6))
        fishing = max(0.0, min(100.0, base_fish - wave * 0.4))
        port_risk = max(0.0, min(100.0, base_port_risk + (i % 5) - 2))
        env_risk = max(0.0, min(100.0, base_env + (i % 3)))
        port_component = max(0.0, min(100.0, 100 - port_risk))
        env_component = max(0.0, min(100.0, 100 - env_risk))
        overall = (
            ocean * 0.25
            + maritime * 0.20
            + fishing * 0.20
            + port_component * 0.20
            + env_component * 0.15
        )
        conf = 72.0 + (i % 4)
        drivers = []
        if sst is not None:
            drivers.append(f"sst_14d={sst:.2f}")
        if cong is not None:
            drivers.append(f"congestion={cong:.1f}")
        drivers.append("source=demo_seed")
        drv = " | ".join(drivers).replace("'", "''")
        rows_sql.append(
            f"(DATE '{d.isoformat()}', '{region}', "
            f"{ocean:.2f}, {maritime:.2f}, {fishing:.2f}, {port_risk:.2f}, {env_risk:.2f}, "
            f"{overall:.2f}, {conf:.2f}, '{drv}', 'v1.0-demo', "
            f"TIMESTAMP '{now.isoformat(sep=' ')}')"
        )

    con.execute(
        """
        INSERT INTO pg.public.fact_wio_intelligence_index (
            index_date, region_id,
            ocean_health_score, maritime_activity_score, fishing_pressure_score,
            port_risk_score, environmental_risk_score, overall_score, confidence_score,
            drivers, methodology_version, created_at
        ) VALUES
        """
        + ",\n".join(rows_sql)
    )
    con.close()
    logger.info("Seeded 21 days of fact_wio_intelligence_index (%s)", region)


if __name__ == "__main__":
    main()

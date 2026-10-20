"""
Create + seed fact_ocean_conditions for Streamlit Ocean Conditions page.

Uses ingestion/.env OCEANWATCH_DB_URI (Supabase). Safe to re-run.
"""

from __future__ import annotations

import logging
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
    logger.info("Ocean conditions → ...@%s", safe)

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{uri}' AS pg (TYPE POSTGRES);")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_ocean_conditions (
            date_key DATE,
            sst_celsius DOUBLE,
            chlorophyll_mg_m3 DOUBLE,
            tide_mean_m DOUBLE,
            tide_min_m DOUBLE,
            tide_max_m DOUBLE,
            region_id VARCHAR,
            created_at TIMESTAMP
        );
        """
    )

    # Demo series: last 30 days Kenya EEZ box averages
    today = date.today()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    con.execute(
        f"DELETE FROM pg.public.fact_ocean_conditions WHERE region_id = 'KENYA_EEZ' "
        f"AND date_key >= DATE '{(today - timedelta(days=40)).isoformat()}';"
    )

    rows = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        # mild seasonal-ish synthetic series
        sst = 27.2 + 0.35 * ((i % 7) - 3) / 3.0 + (0.02 * i)
        chl = 0.28 + 0.04 * ((i % 5) - 2) / 2.0
        tmean = 2.1 + 0.15 * ((i % 3) - 1)
        tmin = tmean - 0.7
        tmax = tmean + 0.9
        rows.append(
            f"(DATE '{d.isoformat()}', {sst:.3f}, {chl:.3f}, {tmean:.3f}, {tmin:.3f}, {tmax:.3f}, "
            f"'KENYA_EEZ', TIMESTAMP '{now.isoformat(sep=' ')}')"
        )

    con.execute(
        "INSERT INTO pg.public.fact_ocean_conditions "
        "(date_key, sst_celsius, chlorophyll_mg_m3, tide_mean_m, tide_min_m, tide_max_m, region_id, created_at) "
        "VALUES " + ",\n".join(rows)
    )
    con.close()
    logger.info("Seeded 30 days of fact_ocean_conditions")


if __name__ == "__main__":
    main()

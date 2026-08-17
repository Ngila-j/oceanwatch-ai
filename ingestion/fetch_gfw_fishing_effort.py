"""
OceanWatch AI — Global Fishing Watch fishing-effort foundation

Requires GFW_API_TOKEN in ingestion/.env
Get a token: https://globalfishingwatch.org/our-apis/

If token is missing, exits softly (DAG-safe).
"""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import duckdb
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).parent / ".env")
GFW_TOKEN = (os.getenv("GFW_API_TOKEN") or os.getenv("GFW_API_KEY") or "").strip()

# Kenya EEZ-ish box
MIN_LON, MAX_LON = 39.0, 45.0
MIN_LAT, MAX_LAT = -5.0, 2.0


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def main():
    logger.info("=== GFW Fishing Effort foundation ===")
    if not GFW_TOKEN:
        logger.warning("GFW_API_TOKEN not set — skipping GFW fetch (add token to ingestion/.env)")
        return

    try:
        import requests
    except ImportError:
        logger.error("requests not installed")
        return

    # 4Wings report-style request (API shapes evolve — adjust when you have a live token)
    end = datetime.utcnow().date()
    start = end - timedelta(days=7)
    url = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
    headers = {"Authorization": f"Bearer {GFW_TOKEN}"}
    params = {
        "spatial-resolution": "LOW",
        "temporal-resolution": "DAY",
        "datasets[0]": "public-global-fishing-effort:latest",
        "date-range": f"{start},{end}",
        "format": "JSON",
    }
    # Geo JSON polygon for region
    geojson = {
        "type": "Polygon",
        "coordinates": [[
            [MIN_LON, MIN_LAT],
            [MAX_LON, MIN_LAT],
            [MAX_LON, MAX_LAT],
            [MIN_LON, MAX_LAT],
            [MIN_LON, MIN_LAT],
        ]],
    }

    logger.info(f"Requesting GFW effort {start} → {end} for Kenya box")
    try:
        resp = requests.post(url, headers=headers, params=params, json=geojson, timeout=120)
        logger.info(f"GFW HTTP {resp.status_code}")
        if resp.status_code >= 400:
            logger.warning(f"GFW response: {resp.text[:500]}")
            logger.warning("Token may be invalid or endpoint schema changed — foundation left in place")
            return
        payload = resp.json()
    except Exception as e:
        logger.warning(f"GFW request failed: {e}")
        return

    # Best-effort flatten (structure varies by GFW version)
    rows = []
    entries = payload if isinstance(payload, list) else payload.get("entries") or payload.get("data") or []
    if isinstance(entries, dict):
        entries = entries.get("entries", [])

    for item in entries if isinstance(entries, list) else []:
        rows.append({
            "effort_date": item.get("date") or item.get("date_time") or str(start),
            "lat": item.get("lat") or item.get("latitude"),
            "lon": item.get("lon") or item.get("longitude"),
            "hours": item.get("hours") or item.get("fishing_hours") or item.get("value"),
            "vessel_id": item.get("vessel_id") or item.get("id"),
            "source": "GFW",
            "loaded_at": datetime.utcnow(),
        })

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")
    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_gfw_fishing_effort (
            effort_date VARCHAR,
            lat DOUBLE,
            lon DOUBLE,
            hours DOUBLE,
            vessel_id VARCHAR,
            source VARCHAR,
            loaded_at TIMESTAMP
        );
    """)

    if not rows:
        logger.warning("GFW returned no flattenable rows — table ensured, no insert")
        con.close()
        return

    df = pd.DataFrame(rows)
    con.register("gfw_df", df)
    con.execute("INSERT INTO pg.public.fact_gfw_fishing_effort SELECT * FROM gfw_df;")
    logger.info(f"Inserted {len(df)} GFW effort rows")
    con.close()
    logger.info("=== GFW fetch completed ===")


if __name__ == "__main__":
    main()
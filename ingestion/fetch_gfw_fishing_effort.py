"""
OceanWatch AI — Global Fishing Watch fishing-effort fetch
Uses 4Wings report API with custom Kenya/WIO polygon.
Requires GFW_API_TOKEN in ingestion/.env
"""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import duckdb
import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).parent / ".env")
GFW_TOKEN = (os.getenv("GFW_API_TOKEN") or os.getenv("GFW_API_KEY") or "").strip()

MIN_LON, MAX_LON = 39.0, 45.0
MIN_LAT, MAX_LAT = -5.0, 2.0


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def build_geojson():
    return {
        "type": "Polygon",
        "coordinates": [[
            [MIN_LON, MIN_LAT],
            [MAX_LON, MIN_LAT],
            [MAX_LON, MAX_LAT],
            [MIN_LON, MAX_LAT],
            [MIN_LON, MIN_LAT],
        ]],
    }


def flatten_entries(payload: dict) -> list:
    rows = []
    entries = payload.get("entries") or []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for key, items in entry.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                rows.append({
                    "effort_date": str(item.get("date") or ""),
                    "lat": item.get("lat"),
                    "lon": item.get("lon"),
                    "hours": item.get("hours"),
                    "flag": item.get("flag"),
                    "vessel_ids": item.get("vesselIDs") or item.get("vessel_ids"),
                    "dataset_key": key,
                    "source": "GFW",
                    "loaded_at": datetime.utcnow(),
                })
    return rows


def main():
    logger.info("=== GFW Fishing Effort fetch ===")
    if not GFW_TOKEN:
        logger.warning("GFW_API_TOKEN not set — skipping")
        return

    end = datetime.utcnow().date() - timedelta(days=3)  # GFW lag ~72h
    start = end - timedelta(days=7)

    url = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
    params = {
        "spatial-resolution": "LOW",
        "temporal-resolution": "DAILY",
        "datasets[0]": "public-global-fishing-effort:latest",
        "date-range": f"{start},{end}",
        "format": "JSON",
    }
    headers = {
        "Authorization": f"Bearer {GFW_TOKEN}",
        "Content-Type": "application/json",
    }
    # Body must wrap geojson under the key "geojson"
    body = {"geojson": build_geojson()}

    logger.info(f"Requesting GFW effort {start} → {end} for Kenya box")
    resp = requests.post(url, headers=headers, params=params, json=body, timeout=180)
    logger.info(f"GFW HTTP {resp.status_code}")

    if resp.status_code >= 400:
        logger.warning(f"GFW response: {resp.text[:800]}")
        return

    payload = resp.json()
    rows = flatten_entries(payload)
    logger.info(f"Flattened {len(rows)} effort cells")

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")
    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_gfw_fishing_effort (
            effort_date VARCHAR,
            lat DOUBLE,
            lon DOUBLE,
            hours DOUBLE,
            flag VARCHAR,
            vessel_ids INTEGER,
            dataset_key VARCHAR,
            source VARCHAR,
            loaded_at TIMESTAMP
        );
    """)

    if not rows:
        logger.warning("No rows to insert (empty report for this window/region)")
        con.close()
        return

    df = pd.DataFrame(rows)
    con.execute("DELETE FROM pg.public.fact_gfw_fishing_effort WHERE source = 'GFW';")
    con.register("gfw_df", df)
    con.execute("INSERT INTO pg.public.fact_gfw_fishing_effort SELECT * FROM gfw_df;")
    logger.info(f"Inserted {len(df)} GFW effort rows")
    con.close()
    logger.info("=== GFW fetch completed ===")


if __name__ == "__main__":
    main()
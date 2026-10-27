"""
Create + seed fact_ais_positions (and light GFW effort) for Intelligence Map.

Uses ingestion/.env OCEANWATCH_DB_URI. Safe to re-run (replaces SAMPLE/DEMO rows).
"""

from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd

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


def get_db_uri() -> str:
    _load_dotenv()
    uri = (os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or "").strip()
    if uri:
        return uri.replace("postgresql+psycopg2://", "postgresql://")
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def seed_ais() -> None:
    uri = get_db_uri()
    safe = uri.split("@")[-1] if "@" in uri else uri
    logger.info("=== Seeding AIS sample positions → ...@%s ===", safe)

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{uri}' AS pg (TYPE POSTGRES);")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_ais_positions (
            position_id INTEGER,
            mmsi VARCHAR,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            flag_country VARCHAR,
            latitude DOUBLE,
            longitude DOUBLE,
            sog DOUBLE,
            cog DOUBLE,
            heading DOUBLE,
            nav_status VARCHAR,
            event_time TIMESTAMP,
            source VARCHAR,
            created_at TIMESTAMP
        );
        """
    )

    vessel_types = ["CARGO", "TANKER", "FISHING", "PASSENGER", "OTHER"]
    flags = ["Kenya", "Panama", "Liberia", "China", "Singapore", "Tanzania", "India"]
    nav_statuses = ["Under way", "At anchor", "Restricted manoeuvrability", "Engaged in fishing"]

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    base = now - timedelta(days=3)
    rows = []
    pid = 1

    vessels = []
    for i in range(15):
        vessels.append(
            {
                "mmsi": f"203{random.randint(100000, 999999)}",
                "name": f"MV {random.choice(['Bahari', 'Nyota', 'Safari', 'Ocean', 'Pwani'])} {random.randint(10, 999)}",
                "type": random.choice(vessel_types),
                "flag": random.choice(flags),
                "lat": random.uniform(-4.5, 1.5),
                "lon": random.uniform(39.5, 44.0),
            }
        )

    for hour in range(0, 72, 2):
        for v in vessels:
            v["lat"] += random.uniform(-0.05, 0.05)
            v["lon"] += random.uniform(-0.05, 0.05)
            v["lat"] = max(-5.0, min(2.0, v["lat"]))
            v["lon"] = max(39.0, min(45.0, v["lon"]))

            sog = round(random.uniform(0.2, 14.5), 1)
            if v["type"] == "FISHING" and random.random() < 0.4:
                sog = round(random.uniform(0.5, 3.5), 1)

            rows.append(
                {
                    "position_id": pid,
                    "mmsi": v["mmsi"],
                    "vessel_name": v["name"],
                    "vessel_type": v["type"],
                    "flag_country": v["flag"],
                    "latitude": round(v["lat"], 5),
                    "longitude": round(v["lon"], 5),
                    "sog": sog,
                    "cog": round(random.uniform(0, 359), 1),
                    "heading": round(random.uniform(0, 359), 1),
                    "nav_status": (
                        "Engaged in fishing"
                        if v["type"] == "FISHING" and sog < 4
                        else random.choice(nav_statuses)
                    ),
                    "event_time": base + timedelta(hours=hour),
                    "source": "SAMPLE",
                    "created_at": now,
                }
            )
            pid += 1

    df = pd.DataFrame(rows)
    con.execute("DELETE FROM pg.public.fact_ais_positions WHERE source = 'SAMPLE';")
    con.register("ais_df", df)
    con.execute("INSERT INTO pg.public.fact_ais_positions SELECT * FROM ais_df;")
    logger.info("Inserted %s AIS SAMPLE positions", len(df))

    # GFW effort cells for map fishing layer
    con.execute(
        """
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
        """
    )
    gfw_rows = []
    for i in range(40):
        gfw_rows.append(
            {
                "effort_date": (now.date() - timedelta(days=i % 10)).isoformat(),
                "lat": round(random.uniform(-4.2, -1.5), 4),
                "lon": round(random.uniform(40.0, 43.5), 4),
                "hours": round(random.uniform(0.5, 12.0), 2),
                "flag": random.choice(["KEN", "TZA", "CHN", "ESP", "UNK"]),
                "vessel_ids": random.randint(1, 8),
                "dataset_key": "public-global-fishing-effort:v3.0",
                "source": "DEMO",
                "loaded_at": now,
            }
        )
    gfw = pd.DataFrame(gfw_rows)
    con.execute("DELETE FROM pg.public.fact_gfw_fishing_effort WHERE source = 'DEMO';")
    con.register("gfw_df", gfw)
    con.execute("INSERT INTO pg.public.fact_gfw_fishing_effort SELECT * FROM gfw_df;")
    logger.info("Inserted %s GFW DEMO effort cells", len(gfw))

    con.close()
    logger.info("=== AIS / GFW sample seeding completed ===")


if __name__ == "__main__":
    seed_ais()

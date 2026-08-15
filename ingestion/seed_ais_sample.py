import os
import logging
from datetime import datetime, timedelta
import random
import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        host, port = "postgres", 5432
    else:
        host, port = "localhost", 5433
    return f"postgresql://postgres:password@{host}:{port}/oceanwatch_db"


def seed_ais():
    logger.info("=== Seeding AIS sample positions (Kenya EEZ) ===")
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")

    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_ais_positions (
            position_id INTEGER,
            mmsi VARCHAR,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            flag_country VARCHAR,
            latitude DOUBLE,
            longitude DOUBLE,
            sog DOUBLE,              -- speed over ground (knots)
            cog DOUBLE,              -- course over ground
            heading DOUBLE,
            nav_status VARCHAR,
            event_time TIMESTAMP,
            source VARCHAR,          -- SAMPLE / AIS / GFW
            created_at TIMESTAMP
        );
    """)

    vessel_types = ["CARGO", "TANKER", "FISHING", "PASSENGER", "OTHER"]
    flags = ["Kenya", "Panama", "Liberia", "China", "Singapore", "Tanzania", "India"]
    nav_statuses = ["Under way", "At anchor", "Restricted manoeuvrability", "Engaged in fishing"]

    rows = []
    base = datetime.utcnow() - timedelta(days=3)
    pid = 1

    # Create a few persistent vessels with tracks
    vessels = []
    for i in range(15):
        vessels.append({
            "mmsi": f"203{random.randint(100000, 999999)}",
            "name": f"MV {random.choice(['Bahari','Nyota','Safari','Ocean','Pwani'])} {random.randint(10,999)}",
            "type": random.choice(vessel_types),
            "flag": random.choice(flags),
            "lat": random.uniform(-4.5, 1.5),
            "lon": random.uniform(39.5, 44.0)
        })

    for hour in range(0, 72, 2):  # every 2 hours for 3 days
        for v in vessels:
            # small movement
            v["lat"] += random.uniform(-0.05, 0.05)
            v["lon"] += random.uniform(-0.05, 0.05)
            v["lat"] = max(-5.0, min(2.0, v["lat"]))
            v["lon"] = max(39.0, min(45.0, v["lon"]))

            sog = round(random.uniform(0.2, 14.5), 1)
            if v["type"] == "FISHING" and random.random() < 0.4:
                sog = round(random.uniform(0.5, 3.5), 1)  # fishing speeds

            rows.append({
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
                "nav_status": "Engaged in fishing" if v["type"] == "FISHING" and sog < 4 else random.choice(nav_statuses),
                "event_time": base + timedelta(hours=hour),
                "source": "SAMPLE",
                "created_at": datetime.utcnow()
            })
            pid += 1

    df = pd.DataFrame(rows)
    con.execute("DELETE FROM pg.public.fact_ais_positions;")
    con.register("ais_df", df)
    con.execute("INSERT INTO pg.public.fact_ais_positions SELECT * FROM ais_df;")
    logger.info(f"Inserted {len(df)} AIS sample positions")
    con.close()
    logger.info("=== AIS sample seeding completed ===")


if __name__ == "__main__":
    seed_ais()
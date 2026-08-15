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


def seed_fishing_activity():
    logger.info("=== Seeding Fishing Activity data (Kenya EEZ) ===")
    db_uri = get_db_uri()

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{db_uri}' AS pg (TYPE POSTGRES);")

    # Create table
    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fishing_activity (
            activity_id INTEGER,
            event_time TIMESTAMP,
            latitude DOUBLE,
            longitude DOUBLE,
            vessel_name VARCHAR,
            vessel_type VARCHAR,          -- LONGLINE, PURSE_SEINE, TRAWLER, ARTISANAL, OTHER
            flag_country VARCHAR,
            fishing_hours DOUBLE,         -- estimated effort
            apparent_effort VARCHAR,      -- LOW, MEDIUM, HIGH
            source VARCHAR,               -- SAMPLE / GFW / AIS
            created_at TIMESTAMP
        );
    """)

    # Kenya EEZ approximate bounds (same as our monitoring box)
    min_lon, max_lon = 39.0, 45.0
    min_lat, max_lat = -5.0, 2.0

    vessel_types = ["LONGLINE", "PURSE_SEINE", "TRAWLER", "ARTISANAL", "OTHER"]
    flags = ["Kenya", "China", "Taiwan", "Spain", "Seychelles", "Tanzania", "Iran", "India"]
    effort_levels = ["LOW", "MEDIUM", "HIGH"]

    rows = []
    base_time = datetime.utcnow() - timedelta(days=14)
    activity_id = 1

    for day in range(14):
        daily_events = random.randint(8, 20)
        for _ in range(daily_events):
            event_time = base_time + timedelta(
                days=day,
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )
            lat = round(random.uniform(min_lat, max_lat), 4)
            lon = round(random.uniform(min_lon, max_lon), 4)
            vessel_type = random.choices(vessel_types, weights=[25, 20, 15, 30, 10])[0]
            flag = random.choice(flags)
            fishing_hours = round(random.uniform(1.5, 14.0), 1)
            effort = random.choices(effort_levels, weights=[40, 40, 20])[0]
            vessel_name = f"FV {random.choice(['Bahari', 'Samaki', 'Ocean', 'Nyota', 'Pwani'])} {random.randint(10, 999)}"

            rows.append({
                "activity_id": activity_id,
                "event_time": event_time,
                "latitude": lat,
                "longitude": lon,
                "vessel_name": vessel_name,
                "vessel_type": vessel_type,
                "flag_country": flag,
                "fishing_hours": fishing_hours,
                "apparent_effort": effort,
                "source": "SAMPLE",
                "created_at": datetime.utcnow()
            })
            activity_id += 1

    df = pd.DataFrame(rows)

    con.execute("DELETE FROM pg.public.fishing_activity;")
    con.register("fish_df", df)
    con.execute("INSERT INTO pg.public.fishing_activity SELECT * FROM fish_df;")
    logger.info(f"Inserted {len(df)} fishing activity records")

    con.close()
    logger.info("=== Fishing activity seeding completed ===")


if __name__ == "__main__":
    seed_fishing_activity()
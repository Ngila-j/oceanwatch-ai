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


def seed_port_activity():
    logger.info("=== Seeding Mombasa Port Activity data ===")
    db_uri = get_db_uri()

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{db_uri}' AS pg (TYPE POSTGRES);")

    # Create table
    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.port_activity (
            activity_id INTEGER,
            event_time TIMESTAMP,
            event_type VARCHAR,          -- ARRIVAL or DEPARTURE
            vessel_name VARCHAR,
            vessel_type VARCHAR,         -- CONTAINER, TANKER, BULK, FISHING, OTHER
            flag_country VARCHAR,
            draft_m DOUBLE,
            status VARCHAR,              -- AT_PORT, ANCHORED, TRANSITING
            created_at TIMESTAMP
        );
    """)

    # Generate realistic sample data for the last 14 days
    vessel_types = ["CONTAINER", "TANKER", "BULK", "FISHING", "OTHER"]
    flags = ["Kenya", "Panama", "Liberia", "Singapore", "China", "India", "Tanzania", "UAE"]
    prefixes = ["MV", "MT", "FV", "SS"]

    rows = []
    base_time = datetime.utcnow() - timedelta(days=14)
    activity_id = 1

    for day in range(14):
        daily_events = random.randint(4, 12)
        for _ in range(daily_events):
            event_time = base_time + timedelta(days=day, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            event_type = random.choice(["ARRIVAL", "DEPARTURE"])
            vessel_type = random.choices(vessel_types, weights=[40, 20, 15, 15, 10])[0]
            vessel_name = f"{random.choice(prefixes)} {random.choice(['Ocean', 'Swahili', 'Safari', 'Nyota', 'Bahari', 'Mombasa', 'Indian'])} {random.randint(100, 999)}"
            flag = random.choice(flags)
            draft = round(random.uniform(4.5, 14.5), 1)
            status = "IN_PORT" if event_type == "ARRIVAL" else "TRANSITING"

            rows.append({
                "activity_id": activity_id,
                "event_time": event_time,
                "event_type": event_type,
                "vessel_name": vessel_name,
                "vessel_type": vessel_type,
                "flag_country": flag,
                "draft_m": draft,
                "status": status,
                "created_at": datetime.utcnow()
            })
            activity_id += 1

    df = pd.DataFrame(rows)

    # Clear old sample data and insert fresh
    con.execute("DELETE FROM pg.public.port_activity;")
    con.register("port_df", df)
    con.execute("INSERT INTO pg.public.port_activity SELECT * FROM port_df;")
    logger.info(f"Inserted {len(df)} port activity records")

    con.close()
    logger.info("=== Port activity seeding completed ===")


if __name__ == "__main__":
    seed_port_activity()
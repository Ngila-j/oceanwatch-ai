"""Composite port operational risk: traffic + tide (+ baseline)."""
import os
import logging
from datetime import datetime, timedelta
import duckdb
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri():
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def run():
    logger.info("=== Port Operational Risk ===")
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")

    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_port_risk (
            risk_date DATE,
            port_name VARCHAR,
            traffic_score DOUBLE,
            tide_score DOUBLE,
            congestion_score DOUBLE,
            composite_risk DOUBLE,
            risk_level VARCHAR,
            drivers VARCHAR,
            created_at TIMESTAMP
        );
    """)

    port = con.execute("SELECT * FROM pg.public.fact_port_metrics ORDER BY metric_date DESC LIMIT 1").fetchdf()
    tides = con.execute("""
        SELECT observation_time::date AS d,
               avg(tide_height_meters) AS mean_tide,
               max(tide_height_meters) - min(tide_height_meters) AS tide_range
        FROM pg.public.stg_tides
        GROUP BY 1 ORDER BY 1 DESC LIMIT 14
    """).fetchdf()

    traffic_score = 50.0
    congestion_score = 50.0
    tide_score = 40.0
    drivers = []

    if not port.empty:
        m = port.iloc[0]
        congestion_score = float(m.get("congestion_index") or 50)
        baseline = float(m.get("vs_30d_baseline_pct") or 0)
        traffic_score = min(100, max(0, 40 + baseline))
        drivers.append(f"congestion_index={congestion_score:.1f}")
        drivers.append(f"vs_30d_baseline={baseline:+.1f}%")

    if not tides.empty:
        tr = float(tides.iloc[0].get("tide_range") or 1.0)
        # larger tidal range → higher operational complexity
        tide_score = min(100, max(0, tr * 25))
        drivers.append(f"tide_range={tr:.2f}m")

    # weights: traffic 45%, congestion 30%, tide 25%
    composite = 0.45 * traffic_score + 0.30 * congestion_score + 0.25 * tide_score
    if composite >= 70:
        level = "HIGH"
    elif composite >= 45:
        level = "MODERATE"
    else:
        level = "LOW"

    now = datetime.utcnow()
    row = {
        "risk_date": now.date(),
        "port_name": "Mombasa",
        "traffic_score": round(traffic_score, 1),
        "tide_score": round(tide_score, 1),
        "congestion_score": round(congestion_score, 1),
        "composite_risk": round(composite, 1),
        "risk_level": level,
        "drivers": " | ".join(drivers),
        "created_at": now,
    }
    df = pd.DataFrame([row])
    con.execute("DELETE FROM pg.public.fact_port_risk WHERE risk_date = current_date;")
    con.register("pr", df)
    con.execute("INSERT INTO pg.public.fact_port_risk SELECT * FROM pr;")
    logger.info(f"Port risk: {level} ({composite:.1f}) — {drivers}")
    con.close()


if __name__ == "__main__":
    run()
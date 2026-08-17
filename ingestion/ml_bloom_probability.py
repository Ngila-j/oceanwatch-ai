"""Bloom-risk probability from CHL + SST anomaly + persistence (not confirmed HAB)."""
import os
import logging
from datetime import datetime
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
    logger.info("=== Bloom Risk Probability ===")
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")

    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_bloom_risk (
            risk_date DATE,
            region VARCHAR,
            chl_current DOUBLE,
            chl_mean_30d DOUBLE,
            chl_anomaly_pct DOUBLE,
            sst_current DOUBLE,
            persistence_days INTEGER,
            bloom_probability DOUBLE,
            risk_level VARCHAR,
            drivers VARCHAR,
            created_at TIMESTAMP
        );
    """)

    chl = con.execute("""
        SELECT date_key, chlorophyll_mg_m3 AS chl
        FROM pg.public.fact_ocean_conditions
        WHERE chlorophyll_mg_m3 IS NOT NULL
        ORDER BY date_key
    """).fetchdf()

    sst = con.execute("""
        SELECT date_key, sst_celsius AS sst
        FROM pg.public.fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL
        ORDER BY date_key
    """).fetchdf()

    if chl.empty:
        logger.warning("No CHL data")
        con.close()
        return

    chl["date_key"] = pd.to_datetime(chl["date_key"])
    current_chl = float(chl["chl"].iloc[-1])
    mean_30 = float(chl["chl"].tail(30).mean())
    anomaly_pct = ((current_chl - mean_30) / mean_30 * 100) if mean_30 else 0

    # persistence: consecutive days above mean
    above = (chl["chl"] > mean_30).astype(int).values
    persistence = 0
    for v in reversed(above):
        if v:
            persistence += 1
        else:
            break

    sst_cur = float(sst["sst"].iloc[-1]) if not sst.empty else None

    # Simple probability model (0-100)
    prob = 20.0
    drivers = []
    if anomaly_pct > 20:
        prob += 25
        drivers.append(f"CHL anomaly {anomaly_pct:+.1f}%")
    elif anomaly_pct > 5:
        prob += 12
        drivers.append(f"CHL mild anomaly {anomaly_pct:+.1f}%")
    if persistence >= 3:
        prob += 20
        drivers.append(f"persistence {persistence}d")
    if current_chl >= 0.8:
        prob += 15
        drivers.append(f"CHL level {current_chl:.3f}")
    if sst_cur and sst_cur >= 28:
        prob += 10
        drivers.append(f"warm SST {sst_cur:.2f}°C")

    prob = min(95, max(5, prob))
    if prob >= 70:
        level = "ELEVATED"
    elif prob >= 45:
        level = "WATCH"
    else:
        level = "LOW"

    if not drivers:
        drivers.append("within baseline variability")

    now = datetime.utcnow()
    row = {
        "risk_date": now.date(),
        "region": "Kenya EEZ Monitoring Box",
        "chl_current": round(current_chl, 4),
        "chl_mean_30d": round(mean_30, 4),
        "chl_anomaly_pct": round(anomaly_pct, 2),
        "sst_current": round(sst_cur, 3) if sst_cur else None,
        "persistence_days": persistence,
        "bloom_probability": round(prob, 1),
        "risk_level": level,
        "drivers": " | ".join(drivers),
        "created_at": now,
    }
    df = pd.DataFrame([row])
    con.execute("DELETE FROM pg.public.fact_bloom_risk WHERE risk_date = current_date;")
    con.register("br", df)
    con.execute("INSERT INTO pg.public.fact_bloom_risk SELECT * FROM br;")
    logger.info(f"Bloom risk: {level} ({prob:.1f}%) — {drivers}")
    con.close()


if __name__ == "__main__":
    run()
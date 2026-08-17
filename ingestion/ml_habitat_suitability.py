"""
Predicted habitat suitability from environmental features.
NOT a claim of where fish are — suitability based on available SST/CHL.
"""
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


def suitability_from_sst_chl(sst, chl):
    """
    Simple scored suitability for pelagic productivity proxy.
    Optimal SST ~26-28°C; moderate CHL preferred over extremes.
    """
    if sst is None or chl is None or (isinstance(sst, float) and np.isnan(sst)):
        return 50.0, "insufficient data"

    sst_score = 100 - min(100, abs(sst - 27.0) * 25)  # peak at 27°C
    if 0.15 <= chl <= 0.6:
        chl_score = 80
    elif chl < 0.15:
        chl_score = 40 + chl * 200
    else:
        chl_score = max(20, 80 - (chl - 0.6) * 50)

    score = 0.55 * sst_score + 0.45 * chl_score
    return float(np.clip(score, 0, 100)), f"sst={sst:.2f}, chl={chl:.3f}"


def run():
    logger.info("=== Habitat Suitability ===")
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")

    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_habitat_suitability (
            as_of_date DATE,
            region VARCHAR,
            sst_celsius DOUBLE,
            chlorophyll_mg_m3 DOUBLE,
            suitability_score DOUBLE,
            suitability_class VARCHAR,
            notes VARCHAR,
            created_at TIMESTAMP
        );
    """)

    row = con.execute("""
        SELECT
            (SELECT sst_celsius FROM pg.public.fact_ocean_conditions
             WHERE sst_celsius IS NOT NULL ORDER BY date_key DESC LIMIT 1) AS sst,
            (SELECT chlorophyll_mg_m3 FROM pg.public.fact_ocean_conditions
             WHERE chlorophyll_mg_m3 IS NOT NULL ORDER BY date_key DESC LIMIT 1) AS chl
    """).fetchdf().iloc[0]

    score, notes = suitability_from_sst_chl(row["sst"], row["chl"])
    if score >= 70:
        klass = "HIGH"
    elif score >= 45:
        klass = "MEDIUM"
    else:
        klass = "LOW"

    now = datetime.utcnow()
    out = pd.DataFrame([{
        "as_of_date": now.date(),
        "region": "Kenya EEZ Monitoring Box",
        "sst_celsius": float(row["sst"]) if pd.notnull(row["sst"]) else None,
        "chlorophyll_mg_m3": float(row["chl"]) if pd.notnull(row["chl"]) else None,
        "suitability_score": round(score, 1),
        "suitability_class": klass,
        "notes": f"Predicted suitability from available environmental features ({notes}). Not a fish-presence prediction.",
        "created_at": now,
    }])
    con.execute("DELETE FROM pg.public.fact_habitat_suitability WHERE as_of_date = current_date;")
    con.register("hs", out)
    con.execute("INSERT INTO pg.public.fact_habitat_suitability SELECT * FROM hs;")
    logger.info(f"Habitat suitability: {klass} ({score:.1f})")
    con.close()


if __name__ == "__main__":
    run()
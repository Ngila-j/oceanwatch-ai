import os
import logging
from datetime import datetime
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


def generate_alerts():
    logger.info("=== Generating Coastal Risk Alerts ===")
    db_uri = get_db_uri()

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{db_uri}' AS pg (TYPE POSTGRES);")

    # Ensure table exists
    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.operational_alerts (
            alert_date DATE,
            alert_type VARCHAR,
            severity VARCHAR,
            title VARCHAR,
            message VARCHAR,
            value DOUBLE,
            created_at TIMESTAMP
        );
    """)

    # Get the most recent non-null SST
    sst_row = con.execute("""
        SELECT date_key, sst_celsius
        FROM pg.public.fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL
        ORDER BY date_key DESC
        LIMIT 1
    """).fetchdf()

    # Get the most recent non-null Chlorophyll
    chl_row = con.execute("""
        SELECT date_key, chlorophyll_mg_m3
        FROM pg.public.fact_ocean_conditions
        WHERE chlorophyll_mg_m3 IS NOT NULL
        ORDER BY date_key DESC
        LIMIT 1
    """).fetchdf()

    alerts = []
    today = datetime.utcnow().date()

    # --- SST Alerts ---
    if not sst_row.empty:
        sst = float(sst_row.iloc[0]["sst_celsius"])
        sst_date = sst_row.iloc[0]["date_key"]

        if sst >= 30.0:
            severity, title = "CRITICAL", "Critical Sea Surface Temperature"
            msg = f"SST reached {sst:.2f}°C on {sst_date}. Elevated risk of coral stress and fisheries impact."
        elif sst >= 29.0:
            severity, title = "WARNING", "Elevated Sea Surface Temperature"
            msg = f"SST at {sst:.2f}°C on {sst_date}. Monitor for thermal stress."
        elif sst >= 27.5:
            severity, title = "INFO", "Warm Sea Surface Temperature"
            msg = f"SST at {sst:.2f}°C on {sst_date}. Slightly warmer than typical conditions."
        else:
            severity = None

        if severity:
            alerts.append({
                "alert_date": sst_date,
                "alert_type": "SST",
                "severity": severity,
                "title": title,
                "message": msg,
                "value": sst,
                "created_at": datetime.utcnow()
            })

    # --- Chlorophyll Alerts ---
    if not chl_row.empty:
        chl = float(chl_row.iloc[0]["chlorophyll_mg_m3"])
        chl_date = chl_row.iloc[0]["date_key"]

        if chl >= 1.5:
            severity, title = "WARNING", "High Chlorophyll Concentration"
            msg = f"Chlorophyll at {chl:.3f} mg/m³ on {chl_date}. Possible bloom conditions."
        elif chl >= 0.6:
            severity, title = "INFO", "Elevated Chlorophyll"
            msg = f"Chlorophyll at {chl:.3f} mg/m³ on {chl_date}. Increased primary productivity."
        else:
            severity = None

        if severity:
            alerts.append({
                "alert_date": chl_date,
                "alert_type": "CHLOROPHYLL",
                "severity": severity,
                "title": title,
                "message": msg,
                "value": chl,
                "created_at": datetime.utcnow()
            })

    # System heartbeat (always written)
    sst_val = float(sst_row.iloc[0]["sst_celsius"]) if not sst_row.empty else None
    chl_val = float(chl_row.iloc[0]["chlorophyll_mg_m3"]) if not chl_row.empty else None

    alerts.append({
        "alert_date": today,
        "alert_type": "SYSTEM",
        "severity": "INFO",
        "title": "Oceanwatch Monitoring Active",
        "message": f"Latest SST={sst_val} | Latest CHL={chl_val}",
        "value": None,
        "created_at": datetime.utcnow()
    })

    alerts_df = pd.DataFrame(alerts)
    con.register("alerts_df", alerts_df)
    con.execute("INSERT INTO pg.public.operational_alerts SELECT * FROM alerts_df;")
    logger.info(f"Generated {len(alerts)} alerts")

    con.close()
    logger.info("=== Alert generation completed ===")


if __name__ == "__main__":
    generate_alerts()
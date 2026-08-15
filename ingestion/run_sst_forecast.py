import os
import logging
from datetime import datetime, timedelta
import duckdb
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        host, port = "postgres", 5432
    else:
        host, port = "localhost", 5433
    return f"postgresql://postgres:password@{host}:{port}/oceanwatch_db"


def run_forecast():
    logger.info("=== SST Forecast Engine Started ===")
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")

    # Ensure forecast table exists
    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_sst_forecast (
            forecast_date DATE,
            forecast_for_date DATE,
            predicted_sst DOUBLE,
            lower_bound DOUBLE,
            upper_bound DOUBLE,
            model_name VARCHAR,
            created_at TIMESTAMP
        );
    """)

    # Load historical SST
    df = con.execute("""
        SELECT date_key, sst_celsius
        FROM pg.public.fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL
        ORDER BY date_key
    """).fetchdf()

    if df.empty or len(df) < 2:
        logger.warning("Not enough SST history for forecasting")
        con.close()
        return

    df["date_key"] = pd.to_datetime(df["date_key"])
    df = df.set_index("date_key").sort_index()

    # Simple but robust approach: exponential smoothing + trend
    values = df["sst_celsius"].values
    last_date = df.index[-1]
    last_value = values[-1]

    # Short trend from last few points
    if len(values) >= 3:
        trend = (values[-1] - values[-3]) / 2
    else:
        trend = values[-1] - values[-2] if len(values) >= 2 else 0

    # Dampen trend
    trend = trend * 0.6

    forecasts = []
    now = datetime.utcnow()

    for day in range(1, 8):  # 7-day forecast
        pred = last_value + (trend * day)
        # Uncertainty grows with horizon
        uncertainty = 0.15 * day
        forecasts.append({
            "forecast_date": now.date(),
            "forecast_for_date": (last_date + timedelta(days=day)).date(),
            "predicted_sst": round(float(pred), 3),
            "lower_bound": round(float(pred - uncertainty), 3),
            "upper_bound": round(float(pred + uncertainty), 3),
            "model_name": "exp_smoothing_trend_v1",
            "created_at": now
        })

    fdf = pd.DataFrame(forecasts)
    con.execute("DELETE FROM pg.public.fact_sst_forecast WHERE forecast_date = current_date;")
    con.register("fdf", fdf)
    con.execute("INSERT INTO pg.public.fact_sst_forecast SELECT * FROM fdf;")
    logger.info(f"Wrote {len(fdf)} SST forecast rows")

    con.close()
    logger.info("=== SST Forecast Engine completed ===")


if __name__ == "__main__":
    run_forecast()
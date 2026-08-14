import os
import logging
import requests
import pandas as pd
import duckdb
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        host, port = "postgres", 5432
    else:
        host, port = "localhost", 5433
    return f"postgresql://postgres:password@{host}:{port}/oceanwatch_db"


def fetch_noaa_tide_sample() -> pd.DataFrame:
    logger.info("Fetching recent ocean/tide data from NOAA...")

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=3)

    begin = start_date.strftime("%Y%m%d")
    end = end_date.strftime("%Y%m%d")

    # Using a reliable East Coast station for sample data (can be changed later)
    url = (
        "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
        f"?begin_date={begin}"
        f"&end_date={end}"
        "&station=8518750"
        "&product=water_level"
        "&datum=MLLW"
        "&time_zone=gmt"
        "&units=metric"
        "&format=json"
    )

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json().get("data", [])

        if data:
            df = pd.DataFrame(data)
            logger.info(f"Successfully fetched {len(df)} records from NOAA ({begin} to {end}).")
            return df
    except Exception as e:
        logger.warning(f"NOAA API request failed: {e}")

    logger.info("Using local fallback sample data.")
    return pd.DataFrame({
        "t": ["2026-08-11 00:00", "2026-08-11 01:00", "2026-08-12 00:00"],
        "v": [1.23, 1.45, 1.38],
        "s": ["0.015", "0.014", "0.016"],
        "f": ["0,0,0,0", "0,0,0,0", "0,0,0,0"],
        "q": ["v", "v", "v"]
    })


def store_in_postgres(df: pd.DataFrame, table_name: str = "raw_tides") -> None:
    db_uri = get_db_uri()
    logger.info(f"Connecting to database via DuckDB...")

    try:
        con = duckdb.connect()
        con.execute("INSTALL postgres; LOAD postgres;")
        con.execute(f"ATTACH '{db_uri}' AS pg (TYPE POSTGRES);")
        con.register("temp_df", df)
        con.execute(f"CREATE OR REPLACE TABLE pg.public.{table_name} AS SELECT * FROM temp_df;")
        con.close()
        logger.info(f"Data successfully loaded into table: public.{table_name}")
    except Exception as e:
        logger.error(f"Failed to write to PostgreSQL: {e}")
        raise


def main():
    logger.info("=== Oceanwatch Ingestion Started ===")
    start = datetime.utcnow()

    tide_df = fetch_noaa_tide_sample()
    store_in_postgres(tide_df)

    duration = (datetime.utcnow() - start).total_seconds()
    logger.info(f"=== Ingestion completed successfully in {duration:.1f}s ===")


if __name__ == "__main__":
    main()
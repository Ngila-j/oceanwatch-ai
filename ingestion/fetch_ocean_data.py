import os
import logging
import requests
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

# Configure simple logging (Airflow will capture stdout/stderr)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def get_db_uri() -> str:
    """
    Return the correct PostgreSQL connection string.
    - Inside Docker containers → use service name 'postgres' on port 5432
    - Running on host machine → use localhost:5433
    """
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        # Running inside Airflow / Docker network
        host = "postgres"
        port = 5432
    else:
        # Running directly on the Windows/Linux host
        host = "localhost"
        port = 5433

    return f"postgresql://postgres:password@{host}:{port}/oceanwatch_db"

def fetch_noaa_tide_sample() -> pd.DataFrame:
    """
    Fetches sample water level data from NOAA.
    Note: Station 8518750 is The Battery, NY (for testing only).
    Later we will switch to Western Indian Ocean / Mombasa relevant sources
    (Copernicus Marine, regional tide gauges, etc.).
    """
    logger.info("Fetching sample ocean/tide data from NOAA...")

    url = (
        "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
        "?begin_date=20260101"
        "&end_date=20260102"
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
            logger.info(f"Successfully fetched {len(df)} records from NOAA.")
            return df
        else:
            logger.warning("NOAA returned no data rows.")
    except Exception as e:
        logger.warning(f"NOAA API request failed: {e}")

    # Fallback sample so the pipeline can still be tested offline
    logger.info("Using local fallback sample data for pipeline testing.")
    return pd.DataFrame({
        "t": ["2026-06-01 00:00", "2026-06-01 01:00", "2026-06-01 02:00"],
        "v": [1.23, 1.45, 1.38],
        "s": ["0.015", "0.014", "0.016"],
        "f": ["0,0,0,0", "0,0,0,0", "0,0,0,0"],
        "q": ["v", "v", "v"]
    })

def store_in_postgres(df: pd.DataFrame, table_name: str = "raw_tides") -> None:
    """Load the DataFrame into PostgreSQL (PostGIS-enabled)."""
    db_uri = get_db_uri()
    logger.info(f"Connecting to database: {db_uri.replace('password', '***')}")

    try:
        engine = create_engine(db_uri)
        df.to_sql(table_name, engine, if_exists="replace", index=False)
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
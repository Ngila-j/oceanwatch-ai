import os
import logging
import duckdb
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_postgres_connection_string() -> str:
    """Return the correct connection string for use inside Docker."""
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        host = "postgres"
        port = 5432
    else:
        host = "localhost"
        port = 5433
    return f"postgresql://postgres:password@{host}:{port}/oceanwatch_db"

def stage_tides():
    logger.info("=== DuckDB Staging Started ===")
    start = datetime.utcnow()

    pg_conn = get_postgres_connection_string()
    logger.info(f"Connecting to Postgres via DuckDB...")

    con = duckdb.connect()  # in-memory DuckDB

    # Install and load the Postgres scanner
    con.execute("INSTALL postgres;")
    con.execute("LOAD postgres;")

    # Attach the Postgres database
    con.execute(f"ATTACH '{pg_conn}' AS pg (TYPE POSTGRES);")

    # Create a clean staging table
    logger.info("Creating clean staging table stg_tides ...")
    con.execute("""
        CREATE OR REPLACE TABLE pg.public.stg_tides AS
        SELECT
            CAST(t AS TIMESTAMP) AS observation_time,
            CAST(v AS DOUBLE)    AS water_level_m,
            CAST(s AS DOUBLE)    AS sigma,
            f                    AS flags,
            q                    AS quality
        FROM pg.public.raw_tides
        WHERE v IS NOT NULL;
    """)

    # Quick quality check
    count = con.execute("SELECT COUNT(*) FROM pg.public.stg_tides;").fetchone()[0]
    logger.info(f"Staged {count} clean rows into public.stg_tides")

    duration = (datetime.utcnow() - start).total_seconds()
    logger.info(f"=== DuckDB Staging completed in {duration:.1f}s ===")

if __name__ == "__main__":
    stage_tides()

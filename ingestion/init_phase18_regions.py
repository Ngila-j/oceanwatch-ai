"""Phase 18 — regional hierarchy schema."""

import logging
import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri():
    import os

    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def main():
    logger.info("=== Phase 18 regional schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    # Prefer clean Phase 18 shapes (avoid legacy dim_regions conflicts)
    for t in (
        "dim_marine_zones",
        "dim_ports_ref",
        "dim_regions",
        "dim_countries",
    ):
        con.execute(f"DROP TABLE IF EXISTS pg.public.{t} CASCADE")

    con.execute(
        """
        CREATE TABLE pg.public.dim_countries (
            country_id VARCHAR PRIMARY KEY,
            country_name VARCHAR,
            iso3 VARCHAR,
            status VARCHAR,
            notes VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.dim_regions (
            region_id VARCHAR PRIMARY KEY,
            country_id VARCHAR,
            region_name VARCHAR,
            region_type VARCHAR,
            min_lat DOUBLE,
            max_lat DOUBLE,
            min_lon DOUBLE,
            max_lon DOUBLE,
            is_primary BOOLEAN,
            status VARCHAR,
            notes VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.dim_ports_ref (
            port_id VARCHAR PRIMARY KEY,
            country_id VARCHAR,
            region_id VARCHAR,
            port_name VARCHAR,
            lat DOUBLE,
            lon DOUBLE,
            status VARCHAR,
            notes VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.dim_marine_zones (
            zone_id VARCHAR PRIMARY KEY,
            country_id VARCHAR,
            region_id VARCHAR,
            zone_name VARCHAR,
            zone_type VARCHAR,
            status VARCHAR,
            notes VARCHAR
        )
        """
    )
    logger.info("=== Phase 18 schema ready ===")


if __name__ == "__main__":
    main()
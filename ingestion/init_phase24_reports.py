"""Phase 24 — intelligence report engine schema."""

import logging

import duckdb

from db_utils import get_db_uri

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    uri = get_db_uri()
    logger.info("=== Phase 24 reports schema → %s ===", uri.split("@")[-1])
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{uri}' AS pg (TYPE POSTGRES)")

    for t in (
        "dim_report_types",
        "fact_report_runs",
        "fact_report_sections",
    ):
        con.execute(f"DROP TABLE IF EXISTS pg.public.{t} CASCADE")

    con.execute(
        """
        CREATE TABLE pg.public.dim_report_types (
            report_type_id VARCHAR PRIMARY KEY,
            report_name VARCHAR,
            cadence VARCHAR,
            audience VARCHAR,
            status VARCHAR,
            notes VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_report_runs (
            run_id BIGINT,
            report_type_id VARCHAR,
            report_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            title VARCHAR,
            summary VARCHAR,
            overall_status VARCHAR,
            confidence_score DOUBLE,
            section_count INTEGER,
            model_version VARCHAR,
            generated_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_report_sections (
            section_id BIGINT,
            run_id BIGINT,
            section_order INTEGER,
            section_code VARCHAR,
            section_title VARCHAR,
            status VARCHAR,
            metric_value DOUBLE,
            metric_label VARCHAR,
            narrative VARCHAR,
            evidence VARCHAR,
            model_version VARCHAR
        )
        """
    )
    # Seed report type catalog (page joins this)
    con.execute(
        """
        INSERT INTO pg.public.dim_report_types VALUES
        ('daily_ops', 'Daily Operational Brief', 'daily', 'ops', 'active',
         'Port, AIS, risk, and anomaly snapshot for Kenya EEZ'),
        ('weekly_ocean', 'Weekly Ocean Brief', 'weekly', 'leadership', 'active',
         'SST, fishing pressure, bloom, and WIO index rollup')
        """
    )
    con.close()
    logger.info("=== Phase 24 schema ready ===")


if __name__ == "__main__":
    main()

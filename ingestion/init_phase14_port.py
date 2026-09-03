"""Phase 14 — port intelligence schema (Mombasa)."""

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
    logger.info("=== Phase 14 port schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_port_performance (
            metric_date DATE,
            port_name VARCHAR,
            arrivals INTEGER,
            departures INTEGER,
            active_vessels INTEGER,
            container_vessels INTEGER,
            tankers INTEGER,
            fishing_vessels INTEGER,
            avg_waiting_hours DOUBLE,
            congestion_index DOUBLE,
            congestion_level VARCHAR,
            vs_30d_baseline_pct DOUBLE,
            throughput_proxy DOUBLE,
            balance_ratio DOUBLE,
            performance_score DOUBLE,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_port_congestion_forecast (
            forecast_date DATE,
            horizon_day INTEGER,
            port_name VARCHAR,
            predicted_congestion_index DOUBLE,
            predicted_level VARCHAR,
            lower_bound DOUBLE,
            upper_bound DOUBLE,
            model_name VARCHAR,
            mae DOUBLE,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_port_arrival_forecast (
            forecast_date DATE,
            horizon_day INTEGER,
            port_name VARCHAR,
            predicted_arrivals DOUBLE,
            predicted_departures DOUBLE,
            model_name VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_berth_pressure (
            as_of_date DATE,
            port_name VARCHAR,
            active_vessels INTEGER,
            capacity_proxy INTEGER,
            berth_utilization_pct DOUBLE,
            pressure_score DOUBLE,
            pressure_level VARCHAR,
            drivers VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_port_ops_risk (
            as_of_date DATE,
            port_name VARCHAR,
            traffic_score DOUBLE,
            congestion_score DOUBLE,
            tide_score DOUBLE,
            berth_score DOUBLE,
            composite_ops_risk DOUBLE,
            risk_level VARCHAR,
            confidence_score DOUBLE,
            drivers VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    logger.info("=== Phase 14 schema ready ===")


if __name__ == "__main__":
    main()
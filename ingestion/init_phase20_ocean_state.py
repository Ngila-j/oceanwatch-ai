"""Phase 20 — ocean state engine schema (SQLAlchemy / Supabase-safe)."""

import logging

from sqlalchemy import create_engine, text

from db_utils import get_db_uri

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def sa_uri() -> str:
    uri = get_db_uri()
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


def main():
    uri = sa_uri()
    logger.info("=== Phase 20 ocean state schema → %s ===", uri.split("@")[-1])
    eng = create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": 30})

    ddl = [
        "DROP TABLE IF EXISTS fact_marine_hazards CASCADE",
        "DROP TABLE IF EXISTS fact_fisheries_conditions CASCADE",
        "DROP TABLE IF EXISTS fact_ecological_stress CASCADE",
        "DROP TABLE IF EXISTS fact_ocean_state CASCADE",
        """
        CREATE TABLE fact_ocean_state (
            as_of_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            ocean_state_score DOUBLE PRECISION,
            ocean_state_label VARCHAR,
            sst_c DOUBLE PRECISION,
            chl_mg_m3 DOUBLE PRECISION,
            tide_m DOUBLE PRECISION,
            ecology_risk DOUBLE PRECISION,
            fisheries_condition_score DOUBLE PRECISION,
            bloom_risk_score DOUBLE PRECISION,
            habitat_score DOUBLE PRECISION,
            climate_stress DOUBLE PRECISION,
            confidence_score DOUBLE PRECISION,
            freshness_pct DOUBLE PRECISION,
            data_sources_count INTEGER,
            summary VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE fact_ecological_stress (
            as_of_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            stress_score DOUBLE PRECISION,
            stress_level VARCHAR,
            drivers VARCHAR,
            sst_contrib DOUBLE PRECISION,
            chl_contrib DOUBLE PRECISION,
            bloom_contrib DOUBLE PRECISION,
            climate_contrib DOUBLE PRECISION,
            confidence_score DOUBLE PRECISION,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE fact_fisheries_conditions (
            as_of_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            condition_score DOUBLE PRECISION,
            condition_label VARCHAR,
            habitat_score DOUBLE PRECISION,
            thermal_fit DOUBLE PRECISION,
            productivity_proxy DOUBLE PRECISION,
            pressure_penalty DOUBLE PRECISION,
            confidence_score DOUBLE PRECISION,
            notes VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE fact_marine_hazards (
            hazard_id BIGINT,
            as_of_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            hazard_type VARCHAR,
            severity VARCHAR,
            score DOUBLE PRECISION,
            lat DOUBLE PRECISION,
            lon DOUBLE PRECISION,
            narrative VARCHAR,
            source_table VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
    ]
    with eng.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))
    eng.dispose()
    logger.info("=== Phase 20 schema ready ===")


if __name__ == "__main__":
    main()

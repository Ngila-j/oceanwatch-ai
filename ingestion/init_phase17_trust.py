"""Phase 17 — Data Trust schema (SQLAlchemy / OCEANWATCH_DB_URI)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus, urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TABLES = (
    "dim_data_sources",
    "dim_data_products",
    "dim_data_licenses",
    "fact_data_quality_scores",
    "fact_data_lineage",
    "fact_ingestion_runs",
)


def _load_env_file() -> None:
    """Load KEY=VALUE pairs from ingestion/.env without overriding real env."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError as e:
        logger.warning("Could not read %s: %s", env_path, e)


def get_db_uri() -> str:
    """Resolve DB URI: OCEANWATCH_DB_URI → DATABASE_URL → local Docker default."""
    _load_env_file()
    uri = (
        os.getenv("OCEANWATCH_DB_URI")
        or os.getenv("DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or ""
    ).strip()
    if not uri:
        if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
            uri = "postgresql://postgres:password@postgres:5432/oceanwatch_db"
        else:
            uri = "postgresql://postgres:password@localhost:5433/oceanwatch_db"
    if uri.startswith("postgres://"):
        uri = "postgresql://" + uri[len("postgres://") :]
    return uri


def _engine(uri: str | None = None) -> Engine:
    raw = uri or get_db_uri()
    # Soft-mask password in logs
    try:
        parsed = urlparse(raw)
        safe = urlunparse(parsed._replace(netloc=f"{parsed.username or ''}:***@{parsed.hostname}:{parsed.port or 5432}"))
        logger.info("Connecting via SQLAlchemy (%s)", safe)
    except Exception:
        logger.info("Connecting via SQLAlchemy")
    return create_engine(raw, pool_pre_ping=True, connect_args={"connect_timeout": 20})


DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS dim_data_sources (
        source_id VARCHAR PRIMARY KEY,
        provider VARCHAR,
        dataset_name VARCHAR,
        access_mode VARCHAR,
        update_frequency VARCHAR,
        license_code VARCHAR,
        attribution TEXT,
        homepage_url TEXT,
        notes TEXT,
        status VARCHAR,
        created_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_data_products (
        product_id VARCHAR PRIMARY KEY,
        product_name VARCHAR,
        domain VARCHAR,
        grain VARCHAR,
        primary_table VARCHAR,
        source_id VARCHAR,
        license_code VARCHAR,
        refresh_cadence VARCHAR,
        owner_team VARCHAR,
        sensitivity VARCHAR,
        description TEXT,
        status VARCHAR,
        created_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_data_licenses (
        license_code VARCHAR PRIMARY KEY,
        license_name VARCHAR,
        commercial_use_allowed BOOLEAN,
        share_alike BOOLEAN,
        attribution_required BOOLEAN,
        summary TEXT,
        url TEXT,
        oceanwatch_notes TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_data_quality_scores (
        score_id BIGINT PRIMARY KEY,
        product_id VARCHAR,
        as_of_date DATE,
        completeness_pct DOUBLE PRECISION,
        freshness_hours DOUBLE PRECISION,
        validity_pct DOUBLE PRECISION,
        uniqueness_pct DOUBLE PRECISION,
        overall_score DOUBLE PRECISION,
        grade VARCHAR,
        row_count BIGINT,
        issue_notes TEXT,
        model_version VARCHAR,
        computed_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_data_lineage (
        lineage_id BIGINT PRIMARY KEY,
        product_id VARCHAR,
        upstream_product_id VARCHAR,
        transform_name VARCHAR,
        transform_version VARCHAR,
        notes TEXT,
        created_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_ingestion_runs (
        run_id BIGINT PRIMARY KEY,
        pipeline_name VARCHAR,
        product_id VARCHAR,
        started_at TIMESTAMP,
        finished_at TIMESTAMP,
        status VARCHAR,
        rows_in BIGINT,
        rows_out BIGINT,
        error_message TEXT,
        triggered_by VARCHAR,
        model_version VARCHAR
    )
    """,
]

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_dim_data_products_source_id ON dim_data_products (source_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_quality_product_id ON fact_data_quality_scores (product_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_quality_computed_at ON fact_data_quality_scores (computed_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_fact_lineage_product_id ON fact_data_lineage (product_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_lineage_upstream ON fact_data_lineage (upstream_product_id)",
    "CREATE INDEX IF NOT EXISTS idx_fact_ingestion_started_at ON fact_ingestion_runs (started_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_fact_ingestion_product_id ON fact_ingestion_runs (product_id)",
    "CREATE INDEX IF NOT EXISTS idx_dim_data_sources_provider ON dim_data_sources (provider)",
]


def ensure_schema(engine: Engine | None = None) -> Engine:
    """Create Phase 17 catalog tables if missing. Optional PHASE17_RESET=1 drops first."""
    eng = engine or _engine()
    reset = os.getenv("PHASE17_RESET", "").strip() in {"1", "true", "TRUE", "yes", "YES"}

    with eng.begin() as conn:
        if reset:
            logger.warning("PHASE17_RESET=1 — dropping Phase 17 catalog tables")
            for t in reversed(TABLES):
                conn.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))

        for ddl in DDL_STATEMENTS:
            conn.execute(text(ddl))

        for idx in INDEX_STATEMENTS:
            try:
                conn.execute(text(idx))
            except Exception as e:
                logger.warning("Index skipped: %s (%s)", idx.split("ON")[0].strip(), e)

        logger.info("=== Phase 17 table counts ===")
        for t in TABLES:
            try:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                logger.info("  %s: %s rows", t, n)
            except Exception as e:
                logger.warning("  %s: count failed (%s)", t, e)

    logger.info("=== Phase 17 schema ready ===")
    return eng


def main() -> None:
    logger.info("=== Phase 17 data trust schema ===")
    try:
        ensure_schema()
        sys.exit(0)
    except Exception as e:
        logger.error("init_phase17_trust failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

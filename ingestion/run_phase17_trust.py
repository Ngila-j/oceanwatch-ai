"""
Phase 17 complete — Data Trust & Provenance.
Catalog sources/products/licenses, quality scores, lineage, ingestion run log.
"""

import logging
import random
from datetime import datetime, timedelta

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase17_trust_v1.0"


def get_db_uri():
    import os

    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def connect():
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")
    return con


def cols(con, table):
    try:
        return [
            r[0]
            for r in con.execute(
                """
                SELECT column_name FROM pg.information_schema.columns
                WHERE table_schema = 'public' AND table_name = ?
                """,
                [table],
            ).fetchall()
        ]
    except Exception:
        return []


def write(con, table, df):
    if df is None or df.empty:
        logger.info("%s: 0 rows", table)
        return
    use = [c for c in df.columns if c in cols(con, table)]
    if not use:
        logger.warning("No matching columns for %s", table)
        return
    con.execute(f"DELETE FROM pg.public.{table}")
    con.register("_t", df[use])
    con.execute(
        f"INSERT INTO pg.public.{table} ({', '.join(use)}) SELECT {', '.join(use)} FROM _t"
    )
    logger.info("%s: %s rows", table, len(df))


def q_count(con, table):
    try:
        return int(con.execute(f"SELECT COUNT(*) FROM pg.public.{table}").fetchone()[0])
    except Exception:
        return None


def run():
    logger.info("=== Phase 17 Data Trust ===")
    now = datetime.utcnow()
    con = connect()

    licenses = pd.DataFrame(
        [
            dict(
                license_code="CC_BY_NC",
                license_name="Creative Commons BY-NC",
                redistribution="restricted",
                commercial_use="no",
                attribution_required=True,
                notes="Typical for GFW non-commercial API use",
            ),
            dict(
                license_code="NOAA_OPEN",
                license_name="NOAA public data products",
                redistribution="yes",
                commercial_use="yes",
                attribution_required=True,
                notes="Confirm per product terms",
            ),
            dict(
                license_code="COPERNICUS",
                license_name="Copernicus Marine Service",
                redistribution="yes",
                commercial_use="yes",
                attribution_required=True,
                notes="Acknowledge CMEMS / dataset DOI where required",
            ),
            dict(
                license_code="OW_INTERNAL",
                license_name="OceanWatch derived products",
                redistribution="internal",
                commercial_use="internal",
                attribution_required=True,
                notes="Model and fusion outputs",
            ),
            dict(
                license_code="SAMPLE",
                license_name="Synthetic / sample demo data",
                redistribution="demo",
                commercial_use="no",
                attribution_required=True,
                notes="Not operational ground truth",
            ),
        ]
    )
    write(con, "dim_data_licenses", licenses)

    sources = pd.DataFrame(
        [
            dict(
                source_id="noaa_tides",
                provider="NOAA",
                dataset_name="CO-OPS water levels",
                description="Tide / water level observations via public API",
                geo_coverage="Station-based (demo station)",
                temporal_coverage="Sub-daily samples",
                update_frequency="Daily Airflow task",
                resolution="Station point",
                license_code="NOAA_OPEN",
                access_type="open",
                pipeline="fetch_ocean_data.py",
                status="ACTIVE",
                last_success_at=now,
                last_failure_at=None,
                notes="",
            ),
            dict(
                source_id="cmems_sst",
                provider="Copernicus Marine",
                dataset_name="Global ocean physics — SST (thetao)",
                description="Sea surface temperature subset for Kenya EEZ box",
                geo_coverage="lon 39–45, lat -5–2 (approx Kenya EEZ focus)",
                temporal_coverage="Daily",
                update_frequency="Daily Airflow task",
                resolution="~0.083 degree",
                license_code="COPERNICUS",
                access_type="registered",
                pipeline="fetch_copernicus_ocean.py",
                status="ACTIVE",
                last_success_at=now,
                last_failure_at=None,
                notes="",
            ),
            dict(
                source_id="cmems_chl",
                provider="Copernicus Marine",
                dataset_name="Ocean colour — Chlorophyll-a",
                description="Chlorophyll-a subset for Kenya EEZ box",
                geo_coverage="Kenya EEZ monitoring box",
                temporal_coverage="Daily when available",
                update_frequency="Daily Airflow task",
                resolution="Product-dependent",
                license_code="COPERNICUS",
                access_type="registered",
                pipeline="fetch_copernicus_ocean.py",
                status="ACTIVE",
                last_success_at=now,
                last_failure_at=None,
                notes="",
            ),
            dict(
                source_id="gfw_effort",
                provider="Global Fishing Watch",
                dataset_name="Apparent fishing effort",
                description="Fishing effort cells via GFW API",
                geo_coverage="Kenya / WIO request box",
                temporal_coverage="Multi-day windows",
                update_frequency="Pipeline schedule",
                resolution="Grid cells",
                license_code="CC_BY_NC",
                access_type="token",
                pipeline="fetch_gfw_fishing_effort.py",
                status="ACTIVE",
                last_success_at=now,
                last_failure_at=None,
                notes="Non-commercial license — attribution required",
            ),
            dict(
                source_id="ais_stream",
                provider="AISStream + OceanWatch SAMPLE",
                dataset_name="AIS vessel positions",
                description="Hybrid live AIS and sample tracks for Kenya box",
                geo_coverage="WIO filter / Kenya EEZ",
                temporal_coverage="Near real-time when live; sample otherwise",
                update_frequency="Pipeline",
                resolution="Point",
                license_code="SAMPLE",
                access_type="api_key",
                pipeline="fetch_ais_realtime.py / seed_ais_sample.py",
                status="ACTIVE",
                last_success_at=now,
                last_failure_at=None,
                notes="Live Kenya density often sparse; SAMPLE used for demos",
            ),
            dict(
                source_id="ow_models",
                provider="OceanWatch",
                dataset_name="Derived ML and operational products",
                description="Forecasts, risk scores, anomalies, indices",
                geo_coverage="Kenya EEZ / Mombasa focus",
                temporal_coverage="Daily",
                update_frequency="Daily DAG",
                resolution="Product-level",
                license_code="OW_INTERNAL",
                access_type="internal",
                pipeline="ml_* + phase* runners",
                status="ACTIVE",
                last_success_at=now,
                last_failure_at=None,
                notes="",
            ),
        ]
    )
    write(con, "dim_data_sources", sources)

    products = pd.DataFrame(
        [
            dict(
                product_id="raw_tides",
                source_id="noaa_tides",
                product_name="Raw tide observations",
                description="Table public.raw_tides",
                unit="m",
                methodology="NOAA API JSON → Postgres",
                status="ACTIVE",
            ),
            dict(
                product_id="raw_sst_daily",
                source_id="cmems_sst",
                product_name="Daily SST mean",
                description="Table public.raw_sst_daily",
                unit="°C",
                methodology="NetCDF subset → spatial mean",
                status="ACTIVE",
            ),
            dict(
                product_id="raw_chl_daily",
                source_id="cmems_chl",
                product_name="Daily chlorophyll mean",
                description="Table public.raw_chl_daily",
                unit="mg/m³",
                methodology="NetCDF subset → spatial mean",
                status="ACTIVE",
            ),
            dict(
                product_id="fact_ocean_conditions",
                source_id="ow_models",
                product_name="Ocean conditions fact",
                description="dbt star schema fact",
                unit="mixed",
                methodology="DuckDB stage + dbt models",
                status="ACTIVE",
            ),
            dict(
                product_id="fact_gfw_fishing_effort",
                source_id="gfw_effort",
                product_name="GFW fishing effort",
                description="Table public.fact_gfw_fishing_effort",
                unit="hours",
                methodology="GFW API flatten → Postgres",
                status="ACTIVE",
            ),
            dict(
                product_id="fact_ais_positions",
                source_id="ais_stream",
                product_name="AIS positions",
                description="Table public.fact_ais_positions",
                unit="point",
                methodology="WebSocket parse and/or SAMPLE seed",
                status="ACTIVE",
            ),
            dict(
                product_id="fact_port_ops_risk",
                source_id="ow_models",
                product_name="Port operational risk",
                description="Phase 14 product",
                unit="0–100 score",
                methodology="Composite of traffic, congestion, tide, berth",
                status="ACTIVE",
            ),
            dict(
                product_id="fact_ocean_risk_fusion",
                source_id="ow_models",
                product_name="Ocean risk fusion",
                description="Phase 13 product",
                unit="0–100 score",
                methodology="Weighted climate + bloom + habitat stress",
                status="ACTIVE",
            ),
            dict(
                product_id="fact_illegal_fishing_risk",
                source_id="ow_models",
                product_name="Fisheries activity risk heuristic",
                description="Phase 15 product — not legal determination",
                unit="0–100 score",
                methodology="GFW + hotspots + AIS + anomaly pressure",
                status="ACTIVE",
            ),
            dict(
                product_id="wio_oii",
                source_id="ow_models",
                product_name="WIO Ocean Intelligence Index",
                description="Table public.fact_wio_intelligence_index",
                unit="0–100",
                methodology="WIO-OII v0.2 weighted components",
                status="ACTIVE",
            ),
        ]
    )
    write(con, "dim_data_products", products)

    # Ingestion runs with optional live row counts
    table_map = {
        "noaa_tides": "raw_tides",
        "cmems_sst": "raw_sst_daily",
        "cmems_chl": "raw_chl_daily",
        "gfw_effort": "fact_gfw_fishing_effort",
        "ais_stream": "fact_ais_positions",
        "ow_models": "fact_ocean_conditions",
    }
    runs = []
    for _, s in sources.iterrows():
        sid = s["source_id"]
        n = q_count(con, table_map.get(sid, "fact_ocean_conditions"))
        runs.append(
            dict(
                run_id=random.randint(10_000_000, 99_999_999),
                source_id=sid,
                product_id=table_map.get(sid),
                started_at=now - timedelta(hours=2),
                finished_at=now - timedelta(hours=1),
                rows_processed=int(n or 0),
                files_processed=1 if n else 0,
                quality_score=90.0 if n else 70.0,
                status="SUCCESS" if n is not None else "UNKNOWN",
                error_message=None,
                model_version=MODEL,
            )
        )
    write(con, "fact_data_ingestion_runs", pd.DataFrame(runs))

    quality_rows = []
    for _, p in products.iterrows():
        n = q_count(con, p["product_id"]) if p["product_id"] not in ("wio_oii",) else q_count(
            con, "fact_wio_intelligence_index"
        )
        if p["product_id"] == "wio_oii":
            n = q_count(con, "fact_wio_intelligence_index")
        completeness = 95.0 if n and n > 0 else 50.0
        freshness = 24.0
        validity = 90.0 if n and n > 0 else 60.0
        qscore = round((completeness + validity + max(0, 100 - freshness)) / 3.0, 1)
        quality_rows.append(
            dict(
                as_of_date=now.date(),
                source_id=p["source_id"],
                product_id=p["product_id"],
                completeness=completeness,
                freshness_hours=freshness,
                validity_score=validity,
                quality_score=qscore,
                notes=f"rows={n}",
                model_version=MODEL,
                created_at=now,
            )
        )
    write(con, "fact_data_quality", pd.DataFrame(quality_rows))

    lineage = pd.DataFrame(
        [
            dict(
                lineage_id=1,
                product_id="fact_ocean_conditions",
                upstream_product_id="raw_sst_daily",
                transform_step="dbt fact_ocean_conditions",
                model_version=MODEL,
                created_at=now,
            ),
            dict(
                lineage_id=2,
                product_id="fact_ocean_conditions",
                upstream_product_id="raw_chl_daily",
                transform_step="dbt fact_ocean_conditions",
                model_version=MODEL,
                created_at=now,
            ),
            dict(
                lineage_id=3,
                product_id="fact_ocean_conditions",
                upstream_product_id="raw_tides",
                transform_step="dbt / stage tides",
                model_version=MODEL,
                created_at=now,
            ),
            dict(
                lineage_id=4,
                product_id="fact_ocean_risk_fusion",
                upstream_product_id="fact_ocean_conditions",
                transform_step="phase13 run_phase13_ocean",
                model_version=MODEL,
                created_at=now,
            ),
            dict(
                lineage_id=5,
                product_id="wio_oii",
                upstream_product_id="fact_ocean_risk_fusion",
                transform_step="compute_wio_index",
                model_version=MODEL,
                created_at=now,
            ),
            dict(
                lineage_id=6,
                product_id="fact_port_ops_risk",
                upstream_product_id="fact_ocean_conditions",
                transform_step="phase14 run_phase14_port",
                model_version=MODEL,
                created_at=now,
            ),
            dict(
                lineage_id=7,
                product_id="fact_illegal_fishing_risk",
                upstream_product_id="fact_gfw_fishing_effort",
                transform_step="phase15 run_phase15_fisheries",
                model_version=MODEL,
                created_at=now,
            ),
            dict(
                lineage_id=8,
                product_id="fact_illegal_fishing_risk",
                upstream_product_id="fact_ais_positions",
                transform_step="phase15 vessel context",
                model_version=MODEL,
                created_at=now,
            ),
        ]
    )
    write(con, "fact_data_lineage", lineage)

    logger.info("=== Phase 17 complete ===")


if __name__ == "__main__":
    run()
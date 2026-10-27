"""
Phase 17 complete — Data Trust & Provenance (SQLAlchemy).
Catalog sources/products/licenses, quality scores, lineage, ingestion run log.
"""

from __future__ import annotations

import logging
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

_INGESTION_DIR = Path(__file__).resolve().parent
if str(_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_INGESTION_DIR))

from init_phase17_trust import TABLES, ensure_schema, get_db_uri, _engine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase17_trust_v1.0"

# Stable seed IDs for idempotent delete-then-insert
SOURCE_IDS = [
    "SRC_AIS_STREAM",
    "SRC_GFW_EFFORT",
    "SRC_VIIRS_DNB",
    "SRC_SAR_DETECT",
    "SRC_OCEAN_ENV",
    "SRC_PORT_REGISTRY",
    "SRC_EEZ_BOUNDARIES",
    "SRC_SAMPLE_SYNTH",
]
PRODUCT_IDS = [
    "PRD_AIS_POSITIONS",
    "PRD_VESSEL_ANOMALIES",
    "PRD_GFW_EFFORT",
    "PRD_FISHING_HOTSPOTS",
    "PRD_VIIRS_LIGHTS",
    "PRD_SAR_TARGETS",
    "PRD_DARK_VESSEL_RISK",
    "PRD_ENV_CONTEXT",
    "PRD_PORT_CALLS",
    "PRD_EEZ_REGIONS",
    "PRD_THREAT_SCOREBOARD",
    "PRD_SAMPLE_DEMO",
]
LICENSE_CODES = [
    "CC_BY_4",
    "CC_BY_NC_4",
    "ODbL_1",
    "PROPRIETARY_SAMPLE",
    "PUBLIC_DOMAIN_MARK",
    "INTERNAL_USE",
]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def seed_sources(now: datetime) -> pd.DataFrame:
    rows = [
        dict(
            source_id="SRC_AIS_STREAM",
            provider="AIS / terrestrial+satellite aggregate",
            dataset_name="Vessel AIS positions",
            access_mode="API + DB",
            update_frequency="near-real-time",
            license_code="INTERNAL_USE",
            attribution="OceanWatch AIS pipeline",
            homepage_url=None,
            notes="Operational vessel tracking feed used for anomaly and risk products.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            source_id="SRC_GFW_EFFORT",
            provider="Global Fishing Watch",
            dataset_name="Fishing effort (apparent)",
            access_mode="download / API",
            update_frequency="daily-weekly",
            license_code="CC_BY_NC_4",
            attribution="Global Fishing Watch",
            homepage_url="https://globalfishingwatch.org/",
            notes=(
                "GFW apparent fishing effort. CC BY-NC 4.0 — non-commercial use; "
                "attribution required. Not a legal determination of fishing activity."
            ),
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            source_id="SRC_VIIRS_DNB",
            provider="NOAA / NASA VIIRS",
            dataset_name="Day/Night Band lights at night",
            access_mode="raster / derived points",
            update_frequency="daily",
            license_code="PUBLIC_DOMAIN_MARK",
            attribution="NOAA NESDIS / NASA",
            homepage_url="https://www.nesdis.noaa.gov/",
            notes="Night-light detections used as fishing/activity cues (heuristic).",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            source_id="SRC_SAR_DETECT",
            provider="SAR detections (multi-mission)",
            dataset_name="SAR vessel-like targets",
            access_mode="derived table",
            update_frequency="tasking-dependent",
            license_code="INTERNAL_USE",
            attribution="OceanWatch SAR fusion",
            homepage_url=None,
            notes="Synthetic aperture radar candidate targets; may include false positives.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            source_id="SRC_OCEAN_ENV",
            provider="Ocean environment composites",
            dataset_name="SST / chlorophyll / meteo context",
            access_mode="gridded products",
            update_frequency="daily",
            license_code="CC_BY_4",
            attribution="Upstream env data providers via OceanWatch",
            homepage_url=None,
            notes="Environmental context layers for situational awareness.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            source_id="SRC_PORT_REGISTRY",
            provider="Port & berth reference",
            dataset_name="Ports and coastal facilities",
            access_mode="reference DB",
            update_frequency="monthly",
            license_code="ODbL_1",
            attribution="Open port reference compilations",
            homepage_url=None,
            notes="Used for port-call and loitering context.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            source_id="SRC_EEZ_BOUNDARIES",
            provider="Marine regions / EEZ",
            dataset_name="EEZ and management boundaries",
            access_mode="vector polygons",
            update_frequency="static / infrequent",
            license_code="CC_BY_4",
            attribution="MarineRegions / national EEZ sources",
            homepage_url="https://www.marineregions.org/",
            notes="Kenya EEZ and WIO region geometry for spatial filters.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            source_id="SRC_SAMPLE_SYNTH",
            provider="OceanWatch",
            dataset_name="Synthetic demo sample layers",
            access_mode="generated",
            update_frequency="on-demand",
            license_code="PROPRIETARY_SAMPLE",
            attribution="OceanWatch sample data",
            homepage_url=None,
            notes=(
                "SAMPLE ONLY — not for operational enforcement or legal use. "
                "Synthetic rows for UI demos and pipeline tests."
            ),
            status="SAMPLE",
            created_at=now,
        ),
    ]
    return pd.DataFrame(rows)


def seed_licenses() -> pd.DataFrame:
    return pd.DataFrame(
        [
            dict(
                license_code="CC_BY_4",
                license_name="Creative Commons Attribution 4.0",
                commercial_use_allowed=True,
                share_alike=False,
                attribution_required=True,
                summary="Free to share and adapt with attribution.",
                url="https://creativecommons.org/licenses/by/4.0/",
                oceanwatch_notes="Preferred for open reference layers when upstream allows.",
            ),
            dict(
                license_code="CC_BY_NC_4",
                license_name="Creative Commons Attribution-NonCommercial 4.0",
                commercial_use_allowed=False,
                share_alike=False,
                attribution_required=True,
                summary="Non-commercial use only; attribution required.",
                url="https://creativecommons.org/licenses/by-nc/4.0/",
                oceanwatch_notes=(
                    "Applies to Global Fishing Watch effort products used here. "
                    "Do not repackage for commercial resale; keep GFW attribution visible."
                ),
            ),
            dict(
                license_code="ODbL_1",
                license_name="Open Database License 1.0",
                commercial_use_allowed=True,
                share_alike=True,
                attribution_required=True,
                summary="Databases may be used with share-alike on derived DBs.",
                url="https://opendatacommons.org/licenses/odbl/",
                oceanwatch_notes="Watch share-alike obligations on substantial extracts.",
            ),
            dict(
                license_code="PROPRIETARY_SAMPLE",
                license_name="OceanWatch proprietary sample",
                commercial_use_allowed=False,
                share_alike=False,
                attribution_required=True,
                summary="Demo/sample data with redistribution restrictions.",
                url=None,
                oceanwatch_notes=(
                    "SAMPLE restrictions: not operational truth; no enforcement decisions; "
                    "do not present as live intelligence without labeling."
                ),
            ),
            dict(
                license_code="PUBLIC_DOMAIN_MARK",
                license_name="Public Domain / USGov public works",
                commercial_use_allowed=True,
                share_alike=False,
                attribution_required=False,
                summary="Public domain or US government work (verify per dataset).",
                url="https://creativecommons.org/publicdomain/mark/1.0/",
                oceanwatch_notes="Still cite upstream for traceability even when not required.",
            ),
            dict(
                license_code="INTERNAL_USE",
                license_name="Internal / licensed operational feed",
                commercial_use_allowed=False,
                share_alike=False,
                attribution_required=True,
                summary="Internal pipeline or licensed feed — not for public bulk release.",
                url=None,
                oceanwatch_notes="Gate external sharing; follow upstream contract terms.",
            ),
        ]
    )


def seed_products(now: datetime) -> pd.DataFrame:
    rows = [
        dict(
            product_id="PRD_AIS_POSITIONS",
            product_name="AIS positions fact",
            domain="vessel",
            grain="position ping",
            primary_table="fact_ais_positions",
            source_id="SRC_AIS_STREAM",
            license_code="INTERNAL_USE",
            refresh_cadence="continuous",
            owner_team="data-platform",
            sensitivity="operational",
            description="Normalized AIS positions for Kenya EEZ / WIO watchboxes.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            product_id="PRD_VESSEL_ANOMALIES",
            product_name="Vessel anomaly scores",
            domain="risk",
            grain="vessel-day",
            primary_table="fact_vessel_anomalies",
            source_id="SRC_AIS_STREAM",
            license_code="INTERNAL_USE",
            refresh_cadence="hourly",
            owner_team="detection",
            sensitivity="operational",
            description="Heuristic anomaly features (gap, speed, loiter, dark cues).",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            product_id="PRD_GFW_EFFORT",
            product_name="GFW fishing effort cells",
            domain="fisheries",
            grain="cell-day",
            primary_table="fact_gfw_fishing_effort",
            source_id="SRC_GFW_EFFORT",
            license_code="CC_BY_NC_4",
            refresh_cadence="daily",
            owner_team="fisheries",
            sensitivity="restricted-nc",
            description="Apparent fishing effort from GFW (CC BY-NC). Attribution required.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            product_id="PRD_FISHING_HOTSPOTS",
            product_name="Fishing effort hotspots",
            domain="fisheries",
            grain="hotspot snapshot",
            primary_table="fact_fishing_hotspots",
            source_id="SRC_GFW_EFFORT",
            license_code="CC_BY_NC_4",
            refresh_cadence="daily",
            owner_team="fisheries",
            sensitivity="restricted-nc",
            description="Aggregated hotspot ranking derived from GFW effort grid.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            product_id="PRD_VIIRS_LIGHTS",
            product_name="VIIRS night-light detections",
            domain="eo",
            grain="detection",
            primary_table="fact_viirs_detections",
            source_id="SRC_VIIRS_DNB",
            license_code="PUBLIC_DOMAIN_MARK",
            refresh_cadence="daily",
            owner_team="eo",
            sensitivity="operational",
            description="Night-light points used as activity cues.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            product_id="PRD_SAR_TARGETS",
            product_name="SAR vessel-like targets",
            domain="eo",
            grain="detection",
            primary_table="fact_sar_detections",
            source_id="SRC_SAR_DETECT",
            license_code="INTERNAL_USE",
            refresh_cadence="tasking",
            owner_team="eo",
            sensitivity="operational",
            description="SAR candidate targets fused into dark-vessel workflows.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            product_id="PRD_DARK_VESSEL_RISK",
            product_name="Dark vessel risk layers",
            domain="risk",
            grain="event / score",
            primary_table="fact_dark_vessel_risk",
            source_id="SRC_SAR_DETECT",
            license_code="INTERNAL_USE",
            refresh_cadence="hourly",
            owner_team="detection",
            sensitivity="operational",
            description="Combined AIS-gap + SAR/VIIRS heuristic dark-vessel risk.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            product_id="PRD_ENV_CONTEXT",
            product_name="Ocean environment context",
            domain="environment",
            grain="grid-day",
            primary_table="fact_ocean_env",
            source_id="SRC_OCEAN_ENV",
            license_code="CC_BY_4",
            refresh_cadence="daily",
            owner_team="science",
            sensitivity="open",
            description="SST/chl/meteo context for narrative and risk modifiers.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            product_id="PRD_PORT_CALLS",
            product_name="Port call features",
            domain="vessel",
            grain="call event",
            primary_table="fact_port_calls",
            source_id="SRC_PORT_REGISTRY",
            license_code="ODbL_1",
            refresh_cadence="daily",
            owner_team="data-platform",
            sensitivity="operational",
            description="Derived port arrival/departure style features.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            product_id="PRD_EEZ_REGIONS",
            product_name="EEZ region dimension",
            domain="reference",
            grain="polygon",
            primary_table="dim_regions",
            source_id="SRC_EEZ_BOUNDARIES",
            license_code="CC_BY_4",
            refresh_cadence="static",
            owner_team="data-platform",
            sensitivity="open",
            description="Kenya EEZ and related management region polygons.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            product_id="PRD_THREAT_SCOREBOARD",
            product_name="Threat / risk scoreboard",
            domain="risk",
            grain="region snapshot",
            primary_table="fact_threat_scoreboard",
            source_id="SRC_AIS_STREAM",
            license_code="INTERNAL_USE",
            refresh_cadence="hourly",
            owner_team="detection",
            sensitivity="operational",
            description="Rolled-up regional threat indicators for command UI.",
            status="ACTIVE",
            created_at=now,
        ),
        dict(
            product_id="PRD_SAMPLE_DEMO",
            product_name="Sample demo product",
            domain="demo",
            grain="mixed",
            primary_table="fact_sample_demo",
            source_id="SRC_SAMPLE_SYNTH",
            license_code="PROPRIETARY_SAMPLE",
            refresh_cadence="on-demand",
            owner_team="product",
            sensitivity="sample",
            description="SAMPLE ONLY — synthetic rows for demos; not operational.",
            status="SAMPLE",
            created_at=now,
        ),
    ]
    return pd.DataFrame(rows)


def seed_quality(now: datetime) -> pd.DataFrame:
    random.seed(17)
    as_of = now.date()
    specs = [
        ("PRD_AIS_POSITIONS", 500_000, 92.0, 1.5),
        ("PRD_VESSEL_ANOMALIES", 12_000, 88.0, 2.0),
        ("PRD_GFW_EFFORT", 80_000, 90.0, 36.0),
        ("PRD_FISHING_HOTSPOTS", 200, 91.0, 36.0),
        ("PRD_VIIRS_LIGHTS", 5_000, 85.0, 30.0),
        ("PRD_SAR_TARGETS", 1_200, 80.0, 48.0),
        ("PRD_DARK_VESSEL_RISK", 3_500, 84.0, 3.0),
        ("PRD_ENV_CONTEXT", 15_000, 89.0, 24.0),
        ("PRD_PORT_CALLS", 4_000, 87.0, 12.0),
        ("PRD_EEZ_REGIONS", 50, 99.0, 720.0),
        ("PRD_THREAT_SCOREBOARD", 30, 86.0, 2.0),
        ("PRD_SAMPLE_DEMO", 100, 70.0, 0.5),
    ]
    rows = []
    for i, (pid, n, base, fresh_h) in enumerate(specs, start=1):
        completeness = min(100.0, base + random.uniform(-3, 3))
        validity = min(100.0, base + random.uniform(-4, 2))
        uniqueness = min(100.0, 94.0 + random.uniform(-5, 4))
        # freshness: lower hours is better → map into 0-100
        fresh_score = max(40.0, 100.0 - fresh_h * 0.5)
        overall = round(0.35 * completeness + 0.25 * validity + 0.2 * uniqueness + 0.2 * fresh_score, 1)
        if overall >= 90:
            grade = "A"
        elif overall >= 80:
            grade = "B"
        elif overall >= 70:
            grade = "C"
        else:
            grade = "D"
        notes = []
        if fresh_h > 24:
            notes.append(f"freshness_hours={fresh_h}")
        if pid == "PRD_GFW_EFFORT":
            notes.append("GFW CC-BY-NC constraints apply")
        if pid == "PRD_SAMPLE_DEMO":
            notes.append("SAMPLE data — excluded from operational SLAs")
        rows.append(
            dict(
                score_id=17_000_000 + i,
                product_id=pid,
                as_of_date=as_of,
                completeness_pct=round(completeness, 1),
                freshness_hours=float(fresh_h),
                validity_pct=round(validity, 1),
                uniqueness_pct=round(uniqueness, 1),
                overall_score=overall,
                grade=grade,
                row_count=int(n),
                issue_notes="; ".join(notes) if notes else None,
                model_version=MODEL,
                computed_at=now,
            )
        )
    return pd.DataFrame(rows)


def seed_lineage(now: datetime) -> pd.DataFrame:
    edges = [
        (1, "PRD_VESSEL_ANOMALIES", "PRD_AIS_POSITIONS", "anomaly_feature_build", "v1"),
        (2, "PRD_FISHING_HOTSPOTS", "PRD_GFW_EFFORT", "hotspot_aggregate", "v1"),
        (3, "PRD_DARK_VESSEL_RISK", "PRD_AIS_POSITIONS", "ais_gap_features", "v1"),
        (4, "PRD_DARK_VESSEL_RISK", "PRD_SAR_TARGETS", "sar_fuse", "v1"),
        (5, "PRD_DARK_VESSEL_RISK", "PRD_VIIRS_LIGHTS", "viirs_fuse", "v1"),
        (6, "PRD_THREAT_SCOREBOARD", "PRD_VESSEL_ANOMALIES", "scoreboard_rollups", "v1"),
        (7, "PRD_THREAT_SCOREBOARD", "PRD_DARK_VESSEL_RISK", "scoreboard_rollups", "v1"),
        (8, "PRD_THREAT_SCOREBOARD", "PRD_FISHING_HOTSPOTS", "scoreboard_rollups", "v1"),
        (9, "PRD_PORT_CALLS", "PRD_AIS_POSITIONS", "port_call_detect", "v1"),
        (10, "PRD_PORT_CALLS", "PRD_EEZ_REGIONS", "spatial_join_ports", "v1"),
        (11, "PRD_SAMPLE_DEMO", "PRD_AIS_POSITIONS", "sample_subset", "v0"),
    ]
    rows = []
    for lid, pid, up, tname, tver in edges:
        rows.append(
            dict(
                lineage_id=lid,
                product_id=pid,
                upstream_product_id=up,
                transform_name=tname,
                transform_version=tver,
                notes=f"{up} → {pid} via {tname}",
                created_at=now,
            )
        )
    return pd.DataFrame(rows)


def seed_ingestion_runs(now: datetime) -> pd.DataFrame:
    random.seed(1717)
    pipelines = [
        ("ais_ingest", "PRD_AIS_POSITIONS", 120_000, 118_500),
        ("gfw_effort_load", "PRD_GFW_EFFORT", 40_000, 39_800),
        ("viirs_detect", "PRD_VIIRS_LIGHTS", 6_000, 5_400),
        ("sar_ingest", "PRD_SAR_TARGETS", 2_000, 1_850),
        ("anomaly_build", "PRD_VESSEL_ANOMALIES", 15_000, 12_000),
        ("hotspot_build", "PRD_FISHING_HOTSPOTS", 39_800, 180),
        ("dark_risk_build", "PRD_DARK_VESSEL_RISK", 20_000, 3_400),
        ("env_context_load", "PRD_ENV_CONTEXT", 16_000, 15_200),
        ("port_features", "PRD_PORT_CALLS", 8_000, 3_900),
        ("threat_scoreboard", "PRD_THREAT_SCOREBOARD", 5_000, 28),
        ("sample_seed", "PRD_SAMPLE_DEMO", 100, 100),
        ("eez_reference", "PRD_EEZ_REGIONS", 60, 48),
    ]
    rows = []
    rid = 17_100_000
    # ~ recent history
    for day_offset in range(0, 14):
        base = now - timedelta(days=day_offset, hours=random.randint(0, 6))
        for pname, pid, rin, rout in pipelines:
            rid += 1
            started = base - timedelta(minutes=random.randint(5, 90))
            dur = timedelta(minutes=random.randint(2, 40))
            finished = started + dur
            # occasional failure
            status = "SUCCESS"
            err = None
            rows_out = rout + random.randint(-20, 20)
            rows_in = rin + random.randint(-50, 50)
            if random.random() < 0.06:
                status = "FAILED"
                err = "simulated transient upstream timeout"
                rows_out = 0
            elif random.random() < 0.08:
                status = "PARTIAL"
                err = "row-level rejects above soft threshold"
                rows_out = max(0, int(rows_out * 0.7))
            rows.append(
                dict(
                    run_id=rid,
                    pipeline_name=pname,
                    product_id=pid,
                    started_at=started,
                    finished_at=finished if status != "FAILED" else started + timedelta(minutes=1),
                    status=status,
                    rows_in=int(max(0, rows_in)),
                    rows_out=int(max(0, rows_out)),
                    error_message=err,
                    triggered_by="scheduler",
                    model_version=MODEL,
                )
            )
    # keep newest 200-ish by construction; page limits 200
    df = pd.DataFrame(rows).sort_values("started_at", ascending=False)
    return df.head(200).reset_index(drop=True)


def _delete_seed_rows(conn) -> None:
    """Remove prior Phase 17 seed rows by known IDs (idempotent re-seed)."""
    # quality scores: deterministic score_id range
    conn.execute(
        text("DELETE FROM fact_data_quality_scores WHERE score_id BETWEEN 17000001 AND 17999999")
    )
    conn.execute(text("DELETE FROM fact_data_lineage WHERE lineage_id BETWEEN 1 AND 100"))
    conn.execute(
        text("DELETE FROM fact_ingestion_runs WHERE run_id BETWEEN 17100000 AND 17999999")
    )
    # products / sources / licenses by code lists
    if PRODUCT_IDS:
        conn.execute(
            text("DELETE FROM dim_data_products WHERE product_id = ANY(:ids)"),
            {"ids": PRODUCT_IDS},
        )
    if SOURCE_IDS:
        conn.execute(
            text("DELETE FROM dim_data_sources WHERE source_id = ANY(:ids)"),
            {"ids": SOURCE_IDS},
        )
    if LICENSE_CODES:
        conn.execute(
            text("DELETE FROM dim_data_licenses WHERE license_code = ANY(:ids)"),
            {"ids": LICENSE_CODES},
        )


def _insert_df(conn, table: str, df: pd.DataFrame) -> int:
    if df is None or df.empty:
        logger.info("%s: 0 rows", table)
        return 0
    clean = df.copy()
    cols = list(clean.columns)
    col_list = ", ".join(cols)
    param_list = ", ".join(f":{c}" for c in cols)
    sql = text(f"INSERT INTO {table} ({col_list}) VALUES ({param_list})")
    records = []
    for rec in clean.to_dict(orient="records"):
        out = {}
        for k, v in rec.items():
            if v is None:
                out[k] = None
            elif isinstance(v, float) and pd.isna(v):
                out[k] = None
            elif isinstance(v, pd.Timestamp):
                out[k] = v.to_pydatetime()
            elif hasattr(v, "item") and not isinstance(v, (bytes, str)):
                try:
                    out[k] = v.item()
                except Exception:
                    out[k] = v
            else:
                try:
                    if pd.isna(v):
                        out[k] = None
                    else:
                        out[k] = v
                except (ValueError, TypeError):
                    out[k] = v
        records.append(out)
    conn.execute(sql, records)
    logger.info("%s: %s rows", table, len(records))
    return len(records)


def _table_count(conn, table: str) -> int:
    try:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
    except Exception:
        return -1


def run() -> None:
    logger.info("=== Phase 17 Data Trust seed ===")
    try:
        engine: Engine = _engine(get_db_uri())
        ensure_schema(engine)
        now = _now()

        sources = seed_sources(now)
        licenses = seed_licenses()
        products = seed_products(now)
        quality = seed_quality(now)
        lineage = seed_lineage(now)
        runs = seed_ingestion_runs(now)

        with engine.begin() as conn:
            _delete_seed_rows(conn)
            _insert_df(conn, "dim_data_licenses", licenses)
            _insert_df(conn, "dim_data_sources", sources)
            _insert_df(conn, "dim_data_products", products)
            _insert_df(conn, "fact_data_quality_scores", quality)
            _insert_df(conn, "fact_data_lineage", lineage)
            _insert_df(conn, "fact_ingestion_runs", runs)

            logger.info("=== Phase 17 final counts ===")
            for t in TABLES:
                logger.info("  %s: %s", t, _table_count(conn, t))

        print("Phase 17 trust catalog seeded OK")
        with engine.connect() as conn:
            for t in TABLES:
                print(f"  {t}: {_table_count(conn, t)}")
        sys.exit(0)
    except Exception as e:
        logger.error("run_phase17_trust failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    run()

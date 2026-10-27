"""
Phase 18 — WIO regional hierarchy seed (SQLAlchemy / Supabase-safe).

Kenya ACTIVE; Tanzania / Seychelles / Mozambique PLANNED.
Same pipelines later filter by region_id / country_id — no per-country DAG copies.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from db_utils import get_db_uri as _shared_uri
except ImportError:
    _shared_uri = None  # type: ignore

try:
    from init_phase18_regions import ensure_schema
except ImportError:
    ensure_schema = None  # type: ignore

MODEL = "phase18_regions_v1.0"


def get_db_uri() -> str:
    if _shared_uri is not None:
        uri = (_shared_uri() or "").strip()
        if uri:
            return uri
    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass
    uri = (os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or "").strip()
    if uri:
        return uri
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def _engine(uri: str | None = None) -> Engine:
    raw = (uri or get_db_uri()).strip()
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+psycopg2://", 1)
    connect_args: dict = {"connect_timeout": 20}
    if "supabase" in raw or "pooler" in raw or "sslmode=" in raw:
        connect_args["sslmode"] = "require"
    return create_engine(raw, pool_pre_ping=True, connect_args=connect_args, pool_size=1, max_overflow=0)


def _table_cols(conn, table: str) -> list[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t
            ORDER BY ordinal_position
            """
        ),
        {"t": table},
    ).fetchall()
    return [r[0] for r in rows]


def _col_types(conn, table: str) -> dict[str, str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t
            """
        ),
        {"t": table},
    ).fetchall()
    return {r[0]: (r[1] or "").lower() for r in rows}


def _replace_table(conn, table: str, df: pd.DataFrame) -> int:
    if df is None or df.empty:
        logger.info("%s: 0 rows", table)
        return 0
    cols = _table_cols(conn, table)
    types = _col_types(conn, table)
    use = [c for c in df.columns if c in cols]
    if not use:
        logger.warning("%s: no matching columns (have %s)", table, cols)
        return 0
    subset = df[use].copy()

    # Legacy dim_marine_zones.zone_key is INTEGER — drop string keys or hash them.
    numeric = {"integer", "bigint", "smallint", "numeric", "double precision", "real"}
    if table == "dim_marine_zones" and "zone_key" in subset.columns:
        zt = types.get("zone_key", "")
        if zt in numeric:
            import hashlib

            def _zk(v):
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return None
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return int(v)
                s = str(v)
                # stable positive 31-bit int from zone id/key string
                h = hashlib.md5(s.encode("utf-8")).hexdigest()
                return int(h[:8], 16) % 2_000_000_000

            try:
                subset["zone_key"] = subset["zone_key"].map(_zk)
            except Exception:
                subset = subset.drop(columns=["zone_key"])
                use = [c for c in use if c != "zone_key"]
                logger.warning("%s: dropped zone_key (incompatible type %s)", table, zt)

    conn.execute(text(f"DELETE FROM {table}"))
    subset.to_sql(table, con=conn, if_exists="append", index=False, method="multi")
    n = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
    logger.info("%s: %s rows", table, n)
    return int(n or 0)


def _seed_frames() -> dict[str, pd.DataFrame]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    countries = pd.DataFrame(
        [
            dict(
                country_id="KE",
                country_name="Kenya",
                iso3="KEN",
                status="ACTIVE",
                notes="Primary OceanWatch focus",
                created_at=now,
            ),
            dict(
                country_id="TZ",
                country_name="Tanzania",
                iso3="TZA",
                status="PLANNED",
                notes="Same pipelines when activated",
                created_at=now,
            ),
            dict(
                country_id="SC",
                country_name="Seychelles",
                iso3="SYC",
                status="PLANNED",
                notes="",
                created_at=now,
            ),
            dict(
                country_id="MZ",
                country_name="Mozambique",
                iso3="MOZ",
                status="PLANNED",
                notes="Northern channel focus later",
                created_at=now,
            ),
        ]
    )

    regions = pd.DataFrame(
        [
            dict(
                region_id="kenya_eez",
                country_id="KE",
                country="Kenya",
                region_name="Kenya EEZ",
                region_type="EEZ",
                min_lat=-6.0,
                max_lat=3.0,
                min_lon=38.0,
                max_lon=46.0,
                is_primary=True,
                status="ACTIVE",
                notes="Primary monitoring box",
                model_version=MODEL,
                created_at=now,
            ),
            dict(
                region_id="mombasa",
                country_id="KE",
                country="Kenya",
                region_name="Mombasa approaches",
                region_type="PORT_AREA",
                min_lat=-4.3,
                max_lat=-3.8,
                min_lon=39.4,
                max_lon=40.0,
                is_primary=False,
                status="ACTIVE",
                notes="Port intelligence focus",
                model_version=MODEL,
                created_at=now,
            ),
            dict(
                region_id="lamu",
                country_id="KE",
                country="Kenya",
                region_name="Lamu area",
                region_type="COAST",
                min_lat=-2.5,
                max_lat=-1.8,
                min_lon=40.5,
                max_lon=41.5,
                is_primary=False,
                status="ACTIVE",
                notes="Northern Kenya coast",
                model_version=MODEL,
                created_at=now,
            ),
            dict(
                region_id="tanzania_eez",
                country_id="TZ",
                country="Tanzania",
                region_name="Tanzania EEZ (planned)",
                region_type="EEZ",
                min_lat=-11.0,
                max_lat=-4.5,
                min_lon=38.0,
                max_lon=43.0,
                is_primary=False,
                status="PLANNED",
                notes="Activate without new pipeline code",
                model_version=MODEL,
                created_at=now,
            ),
            dict(
                region_id="seychelles_eez",
                country_id="SC",
                country="Seychelles",
                region_name="Seychelles EEZ (planned)",
                region_type="EEZ",
                min_lat=-12.0,
                max_lat=-1.0,
                min_lon=43.0,
                max_lon=58.0,
                is_primary=False,
                status="PLANNED",
                notes="",
                model_version=MODEL,
                created_at=now,
            ),
            dict(
                region_id="mozambique_n",
                country_id="MZ",
                country="Mozambique",
                region_name="Northern Mozambique (planned)",
                region_type="EEZ",
                min_lat=-16.0,
                max_lat=-10.0,
                min_lon=39.0,
                max_lon=43.0,
                is_primary=False,
                status="PLANNED",
                notes="Channel / north focus later",
                model_version=MODEL,
                created_at=now,
            ),
        ]
    )

    ports = pd.DataFrame(
        [
            dict(
                port_id="KE_MBA",
                country_id="KE",
                region_id="mombasa",
                port_name="Mombasa",
                lat=-4.0435,
                lon=39.6682,
                unlocode="KEMBA",
                status="ACTIVE",
                notes="Primary Kenya commercial port",
                created_at=now,
            ),
            dict(
                port_id="KE_Lamu",
                country_id="KE",
                region_id="lamu",
                port_name="Lamu",
                lat=-2.2717,
                lon=40.9020,
                unlocode="KELAM",
                status="ACTIVE",
                notes="Northern corridor / LAPSSET context",
                created_at=now,
            ),
            dict(
                port_id="TZ_DAR",
                country_id="TZ",
                region_id="tanzania_eez",
                port_name="Dar es Salaam",
                lat=-6.8235,
                lon=39.2695,
                unlocode="TZDAR",
                status="PLANNED",
                notes="",
                created_at=now,
            ),
            dict(
                port_id="SC_VIC",
                country_id="SC",
                region_id="seychelles_eez",
                port_name="Victoria",
                lat=-4.6191,
                lon=55.4513,
                unlocode="SCPOV",
                status="PLANNED",
                notes="",
                created_at=now,
            ),
            dict(
                port_id="MZ_PEM",
                country_id="MZ",
                region_id="mozambique_n",
                port_name="Pemba",
                lat=-12.9730,
                lon=40.5170,
                unlocode="MZPOL",
                status="PLANNED",
                notes="Northern Mozambique reference",
                created_at=now,
            ),
        ]
    )

    zones = pd.DataFrame(
        [
            dict(
                zone_id="kenya_eez_box",
                zone_key="kenya_eez_box",
                country_id="KE",
                region_id="kenya_eez",
                zone_name="Kenya EEZ monitoring box",
                zone_type="EEZ_BOX",
                min_lat=-6.0,
                max_lat=3.0,
                min_lon=38.0,
                max_lon=46.0,
                status="ACTIVE",
                notes="Aligned with kenya_eez region",
                created_at=now,
            ),
            dict(
                zone_id="watamu_proxy",
                zone_key="watamu_proxy",
                country_id="KE",
                region_id="kenya_eez",
                zone_name="Watamu MPA proxy",
                zone_type="MPA_PROXY",
                min_lat=-3.45,
                max_lat=-3.30,
                min_lon=39.95,
                max_lon=40.10,
                status="DEMO",
                notes="Placeholder until official polygons are licensed",
                created_at=now,
            ),
            dict(
                zone_id="mombasa_approach",
                zone_key="mombasa_approach",
                country_id="KE",
                region_id="mombasa",
                zone_name="Mombasa approach zone",
                zone_type="PORT_APPROACH",
                min_lat=-4.3,
                max_lat=-3.8,
                min_lon=39.4,
                max_lon=40.0,
                status="ACTIVE",
                notes="Aligned with port intelligence geofence concept",
                created_at=now,
            ),
        ]
    )

    return {
        "dim_countries": countries,
        "dim_regions": regions,
        "dim_ports_ref": ports,
        "dim_marine_zones": zones,
    }


def run() -> None:
    logger.info("=== Phase 18 regional hierarchy ===")
    eng = _engine()
    if ensure_schema is not None:
        ensure_schema(eng)
    else:
        logger.warning("ensure_schema unavailable — assuming tables exist")

    frames = _seed_frames()
    # Per-table transactions so a legacy zone_key type cannot wipe countries/ports.
    for table, df in frames.items():
        try:
            with eng.begin() as conn:
                _replace_table(conn, table, df)
        except Exception as e:
            logger.exception("%s seed failed: %s", table, e)

    try:
        with eng.begin() as conn:
            exists = conn.execute(
                text(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'dim_data_products'
                    """
                )
            ).fetchone()
            if exists:
                conn.execute(
                    text(
                        """
                        INSERT INTO dim_data_products (
                            product_id, source_id, product_name, description,
                            refresh_cadence, grain, status
                        )
                        SELECT
                            'dim_regions', 'ow_models', 'Regional hierarchy',
                            'Phase 18 country/region/port/zone dims', 'n/a',
                            'Static reference seed', 'ACTIVE'
                        WHERE NOT EXISTS (
                            SELECT 1 FROM dim_data_products WHERE product_id = 'dim_regions'
                        )
                        """
                    )
                )
    except Exception as e:
        logger.warning("Catalog product note skipped: %s", e)

    counts = {}
    with eng.connect() as conn:
        for t in frames:
            try:
                counts[t] = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            except Exception as e:
                logger.warning("count %s failed: %s", t, e)
                counts[t] = None

    logger.info(
        "Countries=%s regions=%s ports=%s zones=%s",
        counts.get("dim_countries"),
        counts.get("dim_regions"),
        counts.get("dim_ports_ref"),
        counts.get("dim_marine_zones"),
    )
    if not counts.get("dim_countries"):
        raise RuntimeError("dim_countries empty after seed — page 33 will fail")
    logger.info("=== Phase 18 complete ===")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        logger.exception("Phase 18 seed failed: %s", e)
        sys.exit(1)

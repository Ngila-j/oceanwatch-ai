"""
Phase 18 complete — WIO regional hierarchy.
Kenya ACTIVE; Tanzania / Seychelles / Mozambique PLANNED.
Same pipelines later filter by region_id / country_id — no per-country DAG copies.
"""

import logging
from datetime import datetime

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase18_regions_v1.0"


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
        logger.warning("No columns for %s", table)
        return
    con.execute(f"DELETE FROM pg.public.{table}")
    con.register("_t", df[use])
    con.execute(
        f"INSERT INTO pg.public.{table} ({', '.join(use)}) SELECT {', '.join(use)} FROM _t"
    )
    logger.info("%s: %s rows", table, len(df))


def run():
    logger.info("=== Phase 18 regional hierarchy ===")
    con = connect()

    countries = pd.DataFrame(
        [
            dict(
                country_id="KE",
                country_name="Kenya",
                iso3="KEN",
                status="ACTIVE",
                notes="Primary OceanWatch focus",
            ),
            dict(
                country_id="TZ",
                country_name="Tanzania",
                iso3="TZA",
                status="PLANNED",
                notes="Same pipelines when activated",
            ),
            dict(
                country_id="SC",
                country_name="Seychelles",
                iso3="SYC",
                status="PLANNED",
                notes="",
            ),
            dict(
                country_id="MZ",
                country_name="Mozambique",
                iso3="MOZ",
                status="PLANNED",
                notes="Northern channel focus later",
            ),
        ]
    )

    regions = pd.DataFrame(
        [
            dict(
                region_id="kenya_eez",
                country_id="KE",
                region_name="Kenya EEZ",
                region_type="EEZ",
                min_lat=-6.0,
                max_lat=3.0,
                min_lon=38.0,
                max_lon=46.0,
                is_primary=True,
                status="ACTIVE",
                notes="Primary monitoring box",
            ),
            dict(
                region_id="mombasa",
                country_id="KE",
                region_name="Mombasa approaches",
                region_type="PORT_AREA",
                min_lat=-4.3,
                max_lat=-3.8,
                min_lon=39.4,
                max_lon=40.0,
                is_primary=False,
                status="ACTIVE",
                notes="Port intelligence focus",
            ),
            dict(
                region_id="lamu",
                country_id="KE",
                region_name="Lamu area",
                region_type="COAST",
                min_lat=-2.5,
                max_lat=-1.8,
                min_lon=40.5,
                max_lon=41.5,
                is_primary=False,
                status="PLANNED",
                notes="",
            ),
            dict(
                region_id="tanzania_eez",
                country_id="TZ",
                region_name="Tanzania EEZ",
                region_type="EEZ",
                min_lat=-11.0,
                max_lat=-4.5,
                min_lon=38.0,
                max_lon=45.0,
                is_primary=False,
                status="PLANNED",
                notes="",
            ),
            dict(
                region_id="dar",
                country_id="TZ",
                region_name="Dar es Salaam",
                region_type="PORT_AREA",
                min_lat=-7.0,
                max_lat=-6.5,
                min_lon=39.0,
                max_lon=39.6,
                is_primary=False,
                status="PLANNED",
                notes="",
            ),
            dict(
                region_id="zanzibar",
                country_id="TZ",
                region_name="Zanzibar",
                region_type="COAST",
                min_lat=-6.5,
                max_lat=-5.5,
                min_lon=39.0,
                max_lon=39.7,
                is_primary=False,
                status="PLANNED",
                notes="",
            ),
            dict(
                region_id="seychelles_eez",
                country_id="SC",
                region_name="Seychelles EEZ",
                region_type="EEZ",
                min_lat=-12.0,
                max_lat=-3.0,
                min_lon=45.0,
                max_lon=57.0,
                is_primary=False,
                status="PLANNED",
                notes="",
            ),
            dict(
                region_id="n_moz_channel",
                country_id="MZ",
                region_name="Northern Mozambique Channel",
                region_type="CHANNEL",
                min_lat=-17.0,
                max_lat=-10.0,
                min_lon=39.0,
                max_lon=45.0,
                is_primary=False,
                status="PLANNED",
                notes="",
            ),
        ]
    )

    ports = pd.DataFrame(
        [
            dict(
                port_id="mombasa",
                country_id="KE",
                region_id="mombasa",
                port_name="Mombasa",
                lat=-4.05,
                lon=39.67,
                status="ACTIVE",
                notes="Primary port product",
            ),
            dict(
                port_id="dar",
                country_id="TZ",
                region_id="dar",
                port_name="Dar es Salaam",
                lat=-6.83,
                lon=39.31,
                status="PLANNED",
                notes="",
            ),
        ]
    )

    zones = pd.DataFrame(
        [
            dict(
                zone_id="ke_eez",
                country_id="KE",
                region_id="kenya_eez",
                zone_name="Kenya EEZ",
                zone_type="EEZ",
                status="ACTIVE",
                notes="Legal EEZ boundary not digitized here — monitoring box only",
            ),
            dict(
                zone_id="mpa_proxy_ke",
                country_id="KE",
                region_id="kenya_eez",
                zone_name="Demo MPA proxy",
                zone_type="MPA_PROXY",
                status="DEMO",
                notes="Placeholder until official polygons are licensed",
            ),
            dict(
                zone_id="mombasa_approach",
                country_id="KE",
                region_id="mombasa",
                zone_name="Mombasa approach zone",
                zone_type="PORT_APPROACH",
                status="ACTIVE",
                notes="Aligned with port intelligence geofence concept",
            ),
        ]
    )

    write(con, "dim_countries", countries)
    write(con, "dim_regions", regions)
    write(con, "dim_ports_ref", ports)
    write(con, "dim_marine_zones", zones)

    # Optional: register regions in data catalog as a product note
    try:
        con.execute(
            """
            INSERT INTO pg.public.dim_data_products
            SELECT 'dim_regions', 'ow_models', 'Regional hierarchy',
                   'Phase 18 country/region/port/zone dims', 'n/a',
                   'Static reference seed', 'ACTIVE'
            WHERE NOT EXISTS (
                SELECT 1 FROM pg.public.dim_data_products WHERE product_id = 'dim_regions'
            )
            """
        )
    except Exception as e:
        logger.warning("Catalog product note skipped: %s", e)

    logger.info(
        "Countries=%s regions=%s ports=%s zones=%s",
        len(countries),
        len(regions),
        len(ports),
        len(zones),
    )
    logger.info("=== Phase 18 complete ===")


if __name__ == "__main__":
    run()
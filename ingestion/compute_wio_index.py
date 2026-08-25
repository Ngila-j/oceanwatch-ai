"""WIO-OII v1 — upsert kenya_eez (matches real table columns)."""

import logging
from datetime import datetime, date

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri() -> str:
    import os

    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


def main():
    logger.info("=== WIO-OII v1 (history upsert) ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    drivers = []
    conf_pts = 0

    sst = con.execute(
        """
        SELECT AVG(sst_celsius) FROM (
            SELECT sst_celsius FROM pg.public.fact_ocean_conditions
            WHERE sst_celsius IS NOT NULL
            ORDER BY date_key DESC LIMIT 14
        ) s
        """
    ).fetchone()[0]
    ocean = 70.0
    if sst is not None:
        conf_pts += 1
        drivers.append(f"sst_14d={float(sst):.2f}")
        ocean = clamp(100 - abs(float(sst) - 26.5) * 15)

    ais_n = int(
        con.execute(
            "SELECT COUNT(DISTINCT mmsi) FROM pg.public.fact_ais_positions"
        ).fetchone()[0]
        or 0
    )
    conf_pts += 1
    drivers.append(f"ais_vessels={ais_n}")
    maritime = clamp(40 + min(ais_n, 40))

    try:
        gfw_h = float(
            con.execute(
                "SELECT COALESCE(SUM(hours),0) FROM pg.public.fact_gfw_fishing_effort"
            ).fetchone()[0]
            or 0
        )
    except Exception:
        gfw_h = 0.0
    conf_pts += 1
    drivers.append(f"gfw_hours={gfw_h:.1f}")
    fishing_pressure = clamp(30 + min(gfw_h / 10.0, 50))

    port_risk = 50.0
    try:
        pr = con.execute(
            """
            SELECT composite_risk FROM pg.public.fact_port_risk
            ORDER BY risk_date DESC LIMIT 1
            """
        ).fetchone()
        if pr and pr[0] is not None:
            port_risk = float(pr[0])
            conf_pts += 1
            drivers.append(f"composite_risk={port_risk:.1f}")
    except Exception:
        try:
            ci = con.execute(
                """
                SELECT congestion_index FROM pg.public.fact_port_metrics
                ORDER BY metric_date DESC LIMIT 1
                """
            ).fetchone()
            if ci and ci[0] is not None:
                port_risk = float(ci[0])
                conf_pts += 1
                drivers.append(f"congestion={port_risk:.1f}")
        except Exception:
            pass
    port_component = clamp(100 - port_risk)

    env_risk = 30.0
    try:
        br = con.execute(
            """
            SELECT bloom_probability FROM pg.public.fact_bloom_risk
            ORDER BY risk_date DESC LIMIT 1
            """
        ).fetchone()
        if br and br[0] is not None:
            env_risk = clamp(float(br[0]))
            conf_pts += 1
            drivers.append(f"bloom_prob={float(br[0]):.1f}")
    except Exception:
        pass
    env_component = clamp(100 - env_risk)

    overall = clamp(
        ocean * 0.25
        + maritime * 0.20
        + fishing_pressure * 0.20
        + port_component * 0.20
        + env_component * 0.15
    )
    confidence = clamp(50 + conf_pts * 9)
    idx_day = date.today()
    region = "kenya_eez"
    now = datetime.utcnow()
    drv = " | ".join(drivers)

    con.execute(
        """
        DELETE FROM pg.public.fact_wio_intelligence_index
        WHERE index_date = ? AND region_id = ?
        """,
        [idx_day, region],
    )

    con.execute(
        """
        INSERT INTO pg.public.fact_wio_intelligence_index (
            index_date,
            region_id,
            ocean_health_score,
            maritime_activity_score,
            fishing_pressure_score,
            port_risk_score,
            environmental_risk_score,
            overall_score,
            confidence_score,
            drivers,
            methodology_version,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'v1.0', ?)
        """,
        [
            idx_day,
            region,
            ocean,
            maritime,
            fishing_pressure,
            port_risk,
            env_risk,
            overall,
            confidence,
            drv,
            now,
        ],
    )

    logger.info(
        "WIO-OII v1 %s overall=%.1f confidence=%.1f | %s",
        region,
        overall,
        confidence,
        drv,
    )
    logger.info("=== WIO-OII v1 completed ===")


if __name__ == "__main__":
    main()
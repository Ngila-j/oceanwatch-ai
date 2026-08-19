"""
WIO-OII v0.2 — Western Indian Ocean Ocean Intelligence Index

Weights (prototype):
  Ocean Health 25% | Maritime 20% | Fishing 20% | Port (inv.) 20% | Env (inv.) 15%
"""

import os
import logging
from datetime import date
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

WEIGHTS = {
    "ocean_health": 0.25,
    "maritime_activity": 0.20,
    "fishing_pressure": 0.20,
    "port_risk": 0.20,
    "environmental_risk": 0.15,
}
METHOD = "v0.2"


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def clamp(x, lo=0.0, hi=100.0):
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return lo


def table_columns(conn, table: str):
    rows = conn.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t
            """
        ),
        {"t": table},
    ).fetchall()
    return {r[0] for r in rows}


def pick_score(row: dict, candidates):
    if not row:
        return None
    for c in candidates:
        if c in row and row[c] is not None:
            try:
                return float(row[c])
            except (TypeError, ValueError):
                continue
    return None


def main():
    logger.info("=== WIO-OII %s ===", METHOD)
    engine = create_engine(get_db_uri())
    drivers = []
    data_points = 0

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS fact_wio_intelligence_index"))
        conn.execute(
            text(
                """
                CREATE TABLE fact_wio_intelligence_index (
                    index_date DATE NOT NULL,
                    region_id VARCHAR NOT NULL,
                    ocean_health_score DOUBLE PRECISION,
                    maritime_activity_score DOUBLE PRECISION,
                    fishing_pressure_score DOUBLE PRECISION,
                    port_risk_score DOUBLE PRECISION,
                    environmental_risk_score DOUBLE PRECISION,
                    overall_score DOUBLE PRECISION,
                    confidence_score DOUBLE PRECISION,
                    drivers TEXT,
                    methodology_version VARCHAR DEFAULT 'v0.2',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (index_date, region_id)
                )
                """
            )
        )

        ocean = 65.0
        sst = conn.execute(
            text(
                """
                SELECT AVG(sst_celsius) AS s, COUNT(*) AS n
                FROM fact_ocean_conditions
                WHERE sst_celsius IS NOT NULL
                  AND date_key >= CURRENT_DATE - INTERVAL '14 days'
                """
            )
        ).mappings().first()
        if sst and int(sst["n"] or 0) > 0:
            s = float(sst["s"])
            ocean = clamp(100 - abs(s - 27.0) * 12)
            data_points += 1
            drivers.append(f"sst_14d={s:.2f}")

        maritime = 60.0
        if "fact_ais_positions" in table_columns(conn, "fact_ais_positions") or table_columns(conn, "fact_ais_positions"):
            ais = conn.execute(
                text("SELECT COUNT(*) AS n, COUNT(DISTINCT mmsi) AS vessels FROM fact_ais_positions")
            ).mappings().first()
            if ais and int(ais["n"] or 0) > 0:
                v = int(ais["vessels"] or 0)
                maritime = clamp(40 + min(v * 3, 50))
                data_points += 1
                drivers.append(f"ais_vessels={v}")

        if table_columns(conn, "fact_vessel_anomalies"):
            anom = conn.execute(
                text("SELECT AVG(risk_score) AS avg_risk, COUNT(*) AS n FROM fact_vessel_anomalies")
            ).mappings().first()
            if anom and int(anom["n"] or 0) > 0:
                ar = float(anom["avg_risk"] or 50)
                maritime = clamp(maritime - ar * 0.15)
                data_points += 1
                drivers.append(f"avg_vessel_risk={ar:.1f}")

        fishing = 55.0
        if table_columns(conn, "fact_gfw_fishing_effort"):
            gfw = conn.execute(
                text("SELECT COALESCE(SUM(hours),0) AS h, COUNT(*) AS cells FROM fact_gfw_fishing_effort")
            ).mappings().first()
            if gfw and int(gfw["cells"] or 0) > 0:
                h = float(gfw["h"] or 0)
                fishing = clamp(35 + min(h / 8.0, 55))
                data_points += 1
                drivers.append(f"gfw_hours={h:.1f}")

        port = 70.0
        if table_columns(conn, "fact_port_metrics"):
            pm = conn.execute(
                text("SELECT * FROM fact_port_metrics ORDER BY metric_date DESC LIMIT 1")
            ).mappings().first()
            if pm:
                ci = pick_score(dict(pm), ["congestion_index", "congestion_score"])
                if ci is not None:
                    port = clamp(100 - ci * 0.55)
                    data_points += 1
                    drivers.append(f"congestion={ci}")

        if table_columns(conn, "fact_port_risk"):
            pr = conn.execute(
                text("SELECT * FROM fact_port_risk ORDER BY risk_date DESC LIMIT 1")
            ).mappings().first()
            if pr:
                r = pick_score(
                    dict(pr),
                    ["composite_risk", "congestion_score", "traffic_score", "risk_score"],
                )
                if r is not None:
                    port = clamp(0.5 * port + 0.5 * (100 - r))
                    data_points += 1
                    drivers.append(f"composite_risk={r}")

        env = 70.0
        if table_columns(conn, "fact_bloom_risk"):
            bloom = conn.execute(
                text("SELECT * FROM fact_bloom_risk ORDER BY risk_date DESC LIMIT 1")
            ).mappings().first()
            if bloom:
                bp = pick_score(dict(bloom), ["bloom_probability", "probability"])
                if bp is not None:
                    env = clamp(100 - bp)
                    data_points += 1
                    drivers.append(f"bloom_prob={bp}")

        if table_columns(conn, "fact_habitat_suitability"):
            habitat = conn.execute(
                text("SELECT * FROM fact_habitat_suitability ORDER BY as_of_date DESC LIMIT 1")
            ).mappings().first()
            if habitat:
                hs = pick_score(dict(habitat), ["suitability_score", "score"])
                if hs is not None:
                    env = clamp(0.6 * env + 0.4 * hs)
                    data_points += 1
                    drivers.append(f"habitat={hs}")

        overall = round(
            WEIGHTS["ocean_health"] * ocean
            + WEIGHTS["maritime_activity"] * maritime
            + WEIGHTS["fishing_pressure"] * fishing
            + WEIGHTS["port_risk"] * port
            + WEIGHTS["environmental_risk"] * env,
            1,
        )
        confidence = clamp(40 + data_points * 8, 40, 95)
        idx_date = date.today()
        region_id = "kenya_eez"

        conn.execute(
            text(
                """
                INSERT INTO fact_wio_intelligence_index (
                    index_date, region_id,
                    ocean_health_score, maritime_activity_score, fishing_pressure_score,
                    port_risk_score, environmental_risk_score,
                    overall_score, confidence_score, drivers, methodology_version
                ) VALUES (
                    :d, :r, :ocean, :mar, :fish, :port, :env, :overall, :conf, :drivers, :method
                )
                """
            ),
            {
                "d": idx_date,
                "r": region_id,
                "ocean": round(ocean, 1),
                "mar": round(maritime, 1),
                "fish": round(fishing, 1),
                "port": round(port, 1),
                "env": round(env, 1),
                "overall": overall,
                "conf": round(confidence, 1),
                "drivers": " | ".join(drivers),
                "method": METHOD,
            },
        )

    logger.info("WIO-OII %s overall=%.1f confidence=%.1f | %s", region_id, overall, confidence, " | ".join(drivers))
    logger.info("=== WIO-OII completed ===")


if __name__ == "__main__":
    main()
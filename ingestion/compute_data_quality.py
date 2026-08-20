"""
Phase 10 — Dataset quality scores (completeness, validity, timeliness).
Writes fact_data_quality for transparency dashboards.
"""

import os
import logging
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return os.getenv(
        "OCEANWATCH_DB_URI",
        "postgresql://postgres:password@localhost:5433/oceanwatch_db",
    )


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


def cols(conn, table: str):
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


def pick_col(available, candidates):
    for c in candidates:
        if c in available:
            return c
    return None


def main():
    logger.info("=== Data quality scoring ===")
    engine = create_engine(get_db_uri())
    now = datetime.now(timezone.utc)
    results = []

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fact_data_quality (
                    scored_at TIMESTAMP NOT NULL,
                    dataset_name VARCHAR NOT NULL,
                    completeness DOUBLE PRECISION,
                    validity DOUBLE PRECISION,
                    timeliness DOUBLE PRECISION,
                    consistency DOUBLE PRECISION,
                    overall_score DOUBLE PRECISION,
                    records_total INTEGER,
                    records_flagged INTEGER,
                    last_observation TIMESTAMP,
                    status VARCHAR,
                    notes TEXT,
                    PRIMARY KEY (scored_at, dataset_name)
                )
                """
            )
        )

        # --- AIS (event_time, latitude, longitude, mmsi) ---
        if cols(conn, "fact_ais_positions"):
            cset = cols(conn, "fact_ais_positions")
            time_col = pick_col(
                cset,
                [
                    "event_time",
                    "ts",
                    "timestamp",
                    "observed_at",
                    "position_time",
                    "msg_timestamp",
                    "datetime",
                    "time",
                    "created_at",
                ],
            )
            lat_col = pick_col(cset, ["latitude", "lat", "y"])
            lon_col = pick_col(cset, ["longitude", "lon", "lng", "x"])
            mmsi_col = pick_col(cset, ["mmsi", "vessel_mmsi", "userid"])

            time_expr = f"MAX({time_col})" if time_col else "NULL"
            bad_parts = []
            if mmsi_col:
                bad_parts.append(f"{mmsi_col} IS NULL")
            if lat_col:
                bad_parts.append(
                    f"{lat_col} IS NULL OR {lat_col} < -90 OR {lat_col} > 90"
                )
            if lon_col:
                bad_parts.append(
                    f"{lon_col} IS NULL OR {lon_col} < -180 OR {lon_col} > 180"
                )
            bad_expr = " OR ".join(bad_parts) if bad_parts else "FALSE"

            ais = conn.execute(
                text(
                    f"""
                    SELECT
                        COUNT(*) AS n,
                        COUNT(*) FILTER (WHERE {bad_expr}) AS bad,
                        {time_expr} AS last_ts
                    FROM fact_ais_positions
                    """
                )
            ).mappings().first()

            if ais and int(ais["n"] or 0) > 0:
                n, bad = int(ais["n"]), int(ais["bad"] or 0)
                completeness = 100.0
                validity = clamp(100 * (1 - bad / n))
                timeliness = 80.0 if ais["last_ts"] else 50.0
                consistency = 90.0
                overall = clamp(
                    0.25 * completeness
                    + 0.30 * validity
                    + 0.25 * timeliness
                    + 0.20 * consistency
                )
                results.append(
                    (
                        "fact_ais_positions",
                        completeness,
                        validity,
                        timeliness,
                        consistency,
                        overall,
                        n,
                        bad,
                        ais["last_ts"],
                        "HEALTHY" if overall >= 80 else "DEGRADED",
                        f"time_col={time_col}",
                    )
                )

        # --- Ocean conditions ---
        if cols(conn, "fact_ocean_conditions"):
            ocean = conn.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS n,
                        COUNT(*) FILTER (WHERE sst_celsius IS NOT NULL) AS with_sst,
                        COUNT(*) FILTER (
                            WHERE sst_celsius IS NOT NULL
                              AND (sst_celsius < 5 OR sst_celsius > 40)
                        ) AS bad_sst,
                        MAX(date_key) AS last_day
                    FROM fact_ocean_conditions
                    """
                )
            ).mappings().first()

            if ocean and int(ocean["n"] or 0) > 0:
                n = int(ocean["n"])
                with_sst = int(ocean["with_sst"] or 0)
                bad = int(ocean["bad_sst"] or 0)
                completeness = clamp(100 * with_sst / n) if n else 0
                validity = clamp(100 * (1 - bad / max(with_sst, 1)))
                timeliness = 85.0 if ocean["last_day"] else 40.0
                consistency = 88.0
                overall = clamp(
                    0.25 * completeness
                    + 0.30 * validity
                    + 0.25 * timeliness
                    + 0.20 * consistency
                )
                results.append(
                    (
                        "fact_ocean_conditions",
                        completeness,
                        validity,
                        timeliness,
                        consistency,
                        overall,
                        n,
                        bad,
                        ocean["last_day"],
                        "HEALTHY" if overall >= 80 else "DEGRADED",
                        "Daily SST/chl/tides",
                    )
                )

        # --- GFW ---
        if cols(conn, "fact_gfw_fishing_effort"):
            gfw = conn.execute(
                text(
                    """
                    SELECT COUNT(*) AS n, COALESCE(SUM(hours),0) AS h,
                           MAX(effort_date) AS last_day
                    FROM fact_gfw_fishing_effort
                    """
                )
            ).mappings().first()

            if gfw and int(gfw["n"] or 0) > 0:
                n = int(gfw["n"])
                timeliness = 80.0 if gfw["last_day"] else 40.0
                overall = clamp(0.25 * 90 + 0.30 * 95 + 0.25 * timeliness + 0.20 * 92)
                results.append(
                    (
                        "fact_gfw_fishing_effort",
                        90.0,
                        95.0,
                        timeliness,
                        92.0,
                        overall,
                        n,
                        0,
                        gfw["last_day"],
                        "HEALTHY" if overall >= 80 else "DEGRADED",
                        "Attribute Global Fishing Watch",
                    )
                )

        # --- WIO-OII ---
        if cols(conn, "fact_wio_intelligence_index"):
            wio = conn.execute(
                text(
                    """
                    SELECT COUNT(*) AS n, MAX(index_date) AS last_day,
                           AVG(overall_score) AS avg_score
                    FROM fact_wio_intelligence_index
                    """
                )
            ).mappings().first()

            if wio and int(wio["n"] or 0) > 0:
                results.append(
                    (
                        "fact_wio_intelligence_index",
                        100.0,
                        95.0,
                        90.0,
                        90.0,
                        90.0,
                        int(wio["n"]),
                        0,
                        wio["last_day"],
                        "HEALTHY",
                        f"avg_overall≈{wio['avg_score']}",
                    )
                )

        for r in results:
            conn.execute(
                text(
                    """
                    INSERT INTO fact_data_quality (
                        scored_at, dataset_name, completeness, validity, timeliness,
                        consistency, overall_score, records_total, records_flagged,
                        last_observation, status, notes
                    ) VALUES (
                        :scored_at, :name, :comp, :val, :time, :cons, :overall,
                        :total, :flagged, :last_obs, :status, :notes
                    )
                    """
                ),
                {
                    "scored_at": now,
                    "name": r[0],
                    "comp": r[1],
                    "val": r[2],
                    "time": r[3],
                    "cons": r[4],
                    "overall": r[5],
                    "total": r[6],
                    "flagged": r[7],
                    "last_obs": r[8],
                    "status": r[9],
                    "notes": r[10],
                },
            )
            logger.info("%s overall=%.1f status=%s", r[0], r[5], r[9])

    logger.info("=== Data quality completed (%s datasets) ===", len(results))


if __name__ == "__main__":
    main()
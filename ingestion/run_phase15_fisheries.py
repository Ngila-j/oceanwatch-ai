"""
Phase 15 complete — Fisheries Intelligence (Kenya EEZ).
Effort grid, hotspots, seasonality, risk score (heuristic), fisheries alerts.
Not a legal determination of illegal fishing.
"""

import logging
import random
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase15_fisheries_v1.0"
REGION = "kenya_eez"
DISCLAIMER = (
    "Heuristic decision-support only. Not a finding of illegal fishing or legal liability."
)


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
                WHERE table_schema='public' AND table_name=?
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


def qdf(con, sql):
    try:
        return con.execute(sql).fetchdf()
    except Exception as e:
        logger.warning("Query failed: %s", e)
        return pd.DataFrame()


def load_gfw(con):
    df = qdf(con, "SELECT * FROM pg.public.fact_gfw_fishing_effort")
    if df.empty:
        return df
    rename = {}
    if "latitude" in df.columns and "lat" not in df.columns:
        rename["latitude"] = "lat"
    if "longitude" in df.columns and "lon" not in df.columns:
        rename["longitude"] = "lon"
    if rename:
        df = df.rename(columns=rename)
    if "hours" not in df.columns:
        for c in df.columns:
            if "hour" in c.lower():
                df = df.rename(columns={c: "hours"})
                break
    if "effort_date" not in df.columns:
        for c in ("date", "time", "day"):
            if c in df.columns:
                df = df.rename(columns={c: "effort_date"})
                break
    if "hours" not in df.columns:
        df["hours"] = 1.0
    df["effort_date"] = pd.to_datetime(df.get("effort_date"), errors="coerce")
    df["hours"] = pd.to_numeric(df["hours"], errors="coerce").fillna(0)
    return df.dropna(subset=["effort_date"])


def build_effort_grid(gfw: pd.DataFrame, now):
    if gfw.empty:
        return pd.DataFrame()
    rows = []
    for _, r in gfw.iterrows():
        lat = r.get("lat")
        lon = r.get("lon")
        if pd.isna(lat) or pd.isna(lon):
            # grid cell without coords still kept with nulls
            cell = f"cell_{hash((str(r.get('effort_date')), float(r.get('hours') or 0))) % 10_000_000}"
        else:
            # 0.1 deg cells
            lat_b = round(float(lat), 1)
            lon_b = round(float(lon), 1)
            cell = f"{lat_b}_{lon_b}"
            lat, lon = lat_b, lon_b
        rows.append(
            dict(
                cell_id=cell,
                effort_date=r["effort_date"].date()
                if hasattr(r["effort_date"], "date")
                else r["effort_date"],
                lat=float(lat) if pd.notna(lat) else None,
                lon=float(lon) if pd.notna(lon) else None,
                hours=float(r.get("hours") or 0),
                source="GFW",
                region_id=REGION,
                model_version=MODEL,
                created_at=now,
            )
        )
    return pd.DataFrame(rows)


def build_hotspots(grid: pd.DataFrame, now, top_n=15):
    if grid.empty:
        return pd.DataFrame()
    g = (
        grid.dropna(subset=["lat", "lon"])
        .groupby(["lat", "lon"], as_index=False)
        .agg(total_hours=("hours", "sum"), cell_count=("cell_id", "count"))
    )
    if g.empty:
        # fallback: aggregate by cell_id only
        g = grid.groupby("cell_id", as_index=False).agg(
            total_hours=("hours", "sum"), cell_count=("cell_id", "count")
        )
        g["lat"] = None
        g["lon"] = None
    g = g.sort_values("total_hours", ascending=False).head(top_n)
    mx = float(g["total_hours"].max()) or 1.0
    rows = []
    as_of = now.date()
    for i, (_, r) in enumerate(g.iterrows(), start=1):
        intensity = 100.0 * float(r["total_hours"]) / mx
        rows.append(
            dict(
                hotspot_id=random.randint(10_000_000, 99_999_999),
                as_of_date=as_of,
                lat=r.get("lat"),
                lon=r.get("lon"),
                total_hours=round(float(r["total_hours"]), 2),
                cell_count=int(r["cell_count"]),
                intensity_score=round(intensity, 1),
                hotspot_rank=i,
                region_id=REGION,
                model_version=MODEL,
                created_at=now,
            )
        )
    return pd.DataFrame(rows)


def build_seasonality(gfw: pd.DataFrame, now):
    if gfw.empty:
        return pd.DataFrame()
    df = gfw.copy()
    df["month_num"] = df["effort_date"].dt.month
    names = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December",
    }
    rows = []
    for m, g in df.groupby("month_num"):
        days = g["effort_date"].dt.date.nunique()
        total = float(g["hours"].sum())
        rows.append(
            dict(
                month_num=int(m),
                month_name=names.get(int(m), str(m)),
                total_hours=round(total, 2),
                avg_daily_hours=round(total / days, 2) if days else 0.0,
                observation_days=int(days),
                region_id=REGION,
                model_version=MODEL,
                created_at=now,
            )
        )
    return pd.DataFrame(rows).sort_values("month_num")


def build_risk(con, grid: pd.DataFrame, hotspots: pd.DataFrame, now):
    gfw_hours = float(grid["hours"].sum()) if not grid.empty else 0.0
    hs_intensity = (
        float(hotspots["intensity_score"].max()) if not hotspots.empty else 0.0
    )

    fish_ais = 0
    ais = qdf(
        con,
        """
        SELECT COUNT(DISTINCT mmsi) AS n
        FROM pg.public.fact_ais_positions
        WHERE UPPER(COALESCE(vessel_type, '')) LIKE '%FISH%'
        """,
    )
    if not ais.empty:
        fish_ais = int(ais.iloc[0]["n"] or 0)

    anomaly_pressure = 0.0
    va = qdf(
        con,
        """
        SELECT AVG(risk_score) AS avg_risk, COUNT(*) AS n
        FROM pg.public.fact_vessel_anomalies
        WHERE risk_score >= 50
        """,
    )
    if not va.empty and int(va.iloc[0].get("n") or 0) > 0:
        anomaly_pressure = float(va.iloc[0]["avg_risk"] or 0)

    # Heuristic risk 0-100
    score = 0.0
    drivers = []
    score += min(35.0, gfw_hours / 20.0)
    drivers.append(f"gfw_hours={gfw_hours:.1f}")
    score += min(25.0, hs_intensity * 0.25)
    drivers.append(f"hotspot_intensity={hs_intensity:.1f}")
    score += min(20.0, fish_ais * 2.0)
    drivers.append(f"fishing_ais={fish_ais}")
    score += min(20.0, anomaly_pressure * 0.2)
    drivers.append(f"anomaly_pressure={anomaly_pressure:.1f}")
    score = min(100.0, score)

    if score >= 75:
        level = "HIGH"
    elif score >= 55:
        level = "ELEVATED"
    elif score >= 35:
        level = "WATCH"
    else:
        level = "LOW"

    conf = 70.0
    if gfw_hours <= 0:
        conf = 40.0

    return pd.DataFrame(
        [
            dict(
                as_of_date=now.date(),
                region_id=REGION,
                gfw_hours=round(gfw_hours, 2),
                fishing_vessel_ais=fish_ais,
                hotspot_intensity=round(hs_intensity, 1),
                anomaly_pressure=round(anomaly_pressure, 1),
                risk_score=round(score, 1),
                risk_level=level,
                confidence_score=conf,
                drivers=" | ".join(drivers),
                disclaimer=DISCLAIMER,
                model_version=MODEL,
                created_at=now,
            )
        ]
    )


def build_alerts(risk: pd.DataFrame, hotspots: pd.DataFrame, now):
    rows = []
    if risk is not None and not risk.empty:
        r = risk.iloc[0]
        if str(r.get("risk_level")) in ("ELEVATED", "HIGH", "WATCH"):
            rows.append(
                dict(
                    alert_id=random.randint(10_000_000, 99_999_999),
                    as_of_date=r.get("as_of_date"),
                    region_id=REGION,
                    alert_type="FISHERIES_RISK",
                    severity=r.get("risk_level"),
                    title=f"Fisheries activity risk {r.get('risk_level')}",
                    message=f"{r.get('drivers')} — {DISCLAIMER}",
                    metric_value=float(r.get("risk_score") or 0),
                    status="OPEN",
                    model_version=MODEL,
                    created_at=now,
                )
            )
        if float(r.get("gfw_hours") or 0) >= 100:
            rows.append(
                dict(
                    alert_id=random.randint(10_000_000, 99_999_999),
                    as_of_date=r.get("as_of_date"),
                    region_id=REGION,
                    alert_type="EFFORT_VOLUME",
                    severity="INFO",
                    title="Elevated GFW effort hours in stored window",
                    message=f"Total GFW hours={r.get('gfw_hours')}",
                    metric_value=float(r.get("gfw_hours") or 0),
                    status="OPEN",
                    model_version=MODEL,
                    created_at=now,
                )
            )
    if hotspots is not None and not hotspots.empty:
        top = hotspots.iloc[0]
        if float(top.get("intensity_score") or 0) >= 70:
            rows.append(
                dict(
                    alert_id=random.randint(10_000_000, 99_999_999),
                    as_of_date=top.get("as_of_date"),
                    region_id=REGION,
                    alert_type="HOTSPOT",
                    severity="ELEVATED",
                    title="Strong fishing effort hotspot",
                    message=(
                        f"Rank 1 hours={top.get('total_hours')} "
                        f"at ({top.get('lat')}, {top.get('lon')})"
                    ),
                    metric_value=float(top.get("total_hours") or 0),
                    status="OPEN",
                    model_version=MODEL,
                    created_at=now,
                )
            )
    return pd.DataFrame(rows)


def run():
    logger.info("=== Phase 15 fisheries intelligence ===")
    now = datetime.utcnow()
    con = connect()

    gfw = load_gfw(con)
    logger.info("GFW rows: %s", len(gfw))

    grid = build_effort_grid(gfw, now)
    write(con, "fact_fishing_effort_grid", grid)

    hotspots = build_hotspots(grid, now)
    write(con, "fact_fishing_hotspots", hotspots)

    season = build_seasonality(gfw, now)
    write(con, "fact_fisheries_seasonality", season)

    risk = build_risk(con, grid, hotspots, now)
    write(con, "fact_illegal_fishing_risk", risk)

    alerts = build_alerts(risk, hotspots, now)
    write(con, "fact_fisheries_alerts", alerts)

    if not risk.empty:
        r = risk.iloc[0]
        logger.info(
            "Risk=%s %s | hours=%s | %s",
            r.get("risk_score"),
            r.get("risk_level"),
            r.get("gfw_hours"),
            r.get("drivers"),
        )
    logger.info(
        "Grid=%s hotspots=%s season=%s alerts=%s",
        len(grid),
        len(hotspots),
        len(season),
        len(alerts),
    )
    logger.info("=== Phase 15 complete ===")


if __name__ == "__main__":
    run()
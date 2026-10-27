"""
Phase 15 — Fisheries Intelligence (Kenya EEZ).
Effort grid, hotspots, seasonality, risk score (heuristic), fisheries alerts.
Not a legal determination of illegal fishing.

SQLAlchemy + OCEANWATCH_DB_URI (Supabase-safe).
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from db_utils import get_db_uri

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase15_fisheries_v1.1"
REGION = "kenya_eez"
DISCLAIMER = (
    "Heuristic decision-support only. Not a finding of illegal fishing or legal liability."
)
MONTH_NAMES = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}


def sa_uri() -> str:
    uri = get_db_uri()
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


def engine():
    uri = sa_uri()
    logger.info("Phase 15 → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
    return create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": 30})


def qdf(eng, sql: str) -> pd.DataFrame:
    try:
        return pd.read_sql(text(sql), eng)
    except Exception as e:  # noqa: BLE001
        logger.warning("Query failed: %s", e)
        return pd.DataFrame()


def write(eng, table: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        logger.info("%s: 0 rows", table)
        return
    with eng.begin() as conn:
        conn.execute(text(f"DELETE FROM {table}"))
        df.to_sql(table, conn, if_exists="append", index=False, method="multi")
    logger.info("%s: %s rows", table, len(df))


def _date(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    t = pd.to_datetime(v, errors="coerce")
    if pd.isna(t):
        return None
    if hasattr(t, "date"):
        return t.date()
    return t


def load_gfw(eng) -> pd.DataFrame:
    df = qdf(eng, "SELECT * FROM fact_gfw_fishing_effort")
    if df.empty:
        return df
    rename = {}
    for a, b in [
        ("latitude", "lat"),
        ("longitude", "lon"),
        ("fishing_hours", "hours"),
        ("effort_hours", "hours"),
        ("date", "effort_date"),
    ]:
        if a in df.columns and b not in df.columns:
            rename[a] = b
    if rename:
        df = df.rename(columns=rename)
    if "lat" not in df.columns or "lon" not in df.columns:
        return pd.DataFrame()
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    if "hours" not in df.columns:
        df["hours"] = 1.0
    df["hours"] = pd.to_numeric(df["hours"], errors="coerce").fillna(0)
    df["effort_date"] = pd.to_datetime(df.get("effort_date"), errors="coerce")
    return df.dropna(subset=["lat", "lon", "effort_date"])


def build_effort_grid(gfw: pd.DataFrame, now) -> pd.DataFrame:
    if gfw.empty:
        return pd.DataFrame()
    rows = []
    for _, r in gfw.iterrows():
        lat = float(r["lat"])
        lon = float(r["lon"])
        lat_b = round(lat, 1)
        lon_b = round(lon, 1)
        cell = f"{lat_b}_{lon_b}"
        rows.append(
            dict(
                cell_id=cell,
                effort_date=_date(r["effort_date"]),
                lat=lat_b,
                lon=lon_b,
                hours=round(float(r["hours"]), 3),
                source="GFW",
                region_id=REGION,
                model_version=MODEL,
                created_at=now,
            )
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Aggregate duplicate cells per day
    agg = (
        out.groupby(["cell_id", "effort_date", "lat", "lon", "source", "region_id", "model_version"], as_index=False)
        .agg(hours=("hours", "sum"), created_at=("created_at", "max"))
    )
    return agg


def build_hotspots(grid: pd.DataFrame, now, top_n: int = 25) -> pd.DataFrame:
    if grid is None or grid.empty:
        return pd.DataFrame()
    g = (
        grid.groupby(["cell_id", "lat", "lon"], as_index=False)
        .agg(total_hours=("hours", "sum"), cell_count=("effort_date", "nunique"))
    )
    if g.empty:
        return pd.DataFrame()
    mx = float(g["total_hours"].max()) or 1.0
    g["intensity_score"] = (g["total_hours"] / mx * 100.0).round(1)
    g = g.sort_values("total_hours", ascending=False).head(top_n).reset_index(drop=True)
    g["hotspot_rank"] = g.index + 1
    g["hotspot_id"] = [random.randint(10_000_000, 99_999_999) for _ in range(len(g))]
    g["as_of_date"] = now.date()
    g["region_id"] = REGION
    g["model_version"] = MODEL
    g["created_at"] = now
    return g[
        [
            "hotspot_id",
            "as_of_date",
            "lat",
            "lon",
            "total_hours",
            "cell_count",
            "intensity_score",
            "hotspot_rank",
            "region_id",
            "model_version",
            "created_at",
        ]
    ]


def build_seasonality(gfw: pd.DataFrame, now) -> pd.DataFrame:
    if gfw is None or gfw.empty:
        return pd.DataFrame()
    df = gfw.copy()
    df["month_num"] = df["effort_date"].dt.month
    rows = []
    for m, g in df.groupby("month_num"):
        days = int(g["effort_date"].dt.date.nunique())
        total = float(g["hours"].sum())
        rows.append(
            dict(
                month_num=int(m),
                month_name=MONTH_NAMES.get(int(m), str(m)),
                total_hours=round(total, 2),
                avg_daily_hours=round(total / days, 2) if days else 0.0,
                observation_days=days,
                region_id=REGION,
                model_version=MODEL,
                created_at=now,
            )
        )
    return pd.DataFrame(rows).sort_values("month_num")


def build_risk(eng, gfw: pd.DataFrame, hotspots: pd.DataFrame, now) -> pd.DataFrame:
    gfw_hours = float(gfw["hours"].sum()) if gfw is not None and not gfw.empty else 0.0
    hs_intensity = (
        float(hotspots["intensity_score"].max()) if hotspots is not None and not hotspots.empty else 0.0
    )

    ais = qdf(
        eng,
        """
        SELECT COUNT(DISTINCT mmsi) AS n
        FROM fact_ais_positions
        WHERE UPPER(COALESCE(vessel_type, '')) LIKE '%FISH%'
        """,
    )
    fish_ais = int(ais["n"].iloc[0]) if not ais.empty and pd.notna(ais["n"].iloc[0]) else 0

    an = qdf(
        eng,
        """
        SELECT AVG(risk_score) AS avg_risk, COUNT(*) AS n
        FROM fact_vessel_anomalies
        WHERE risk_score >= 50
        """,
    )
    anomaly_pressure = 0.0
    if not an.empty and pd.notna(an["avg_risk"].iloc[0]):
        anomaly_pressure = float(an["avg_risk"].iloc[0])

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

    conf = 40.0 if gfw_hours <= 0 else 70.0

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


def build_alerts(risk: pd.DataFrame, hotspots: pd.DataFrame, now) -> pd.DataFrame:
    rows = []
    if risk is not None and not risk.empty:
        r = risk.iloc[0]
        if r.get("risk_level") in ("ELEVATED", "HIGH", "WATCH"):
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
        top = hotspots.sort_values("hotspot_rank").iloc[0]
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


def seed_demo_gfw_if_empty(eng) -> pd.DataFrame:
    """If GFW table empty/missing, write a small Kenya EEZ demo sample."""
    existing = qdf(eng, "SELECT * FROM fact_gfw_fishing_effort LIMIT 5")
    if not existing.empty:
        return load_gfw(eng)

    logger.warning("No GFW effort — seeding demo Kenya EEZ cells")
    rng = np.random.default_rng(42)
    base = pd.Timestamp.utcnow().normalize() - pd.Timedelta(days=30)
    rows = []
    # Coastal Kenya EEZ-ish grid
    for day in range(0, 30, 2):
        for _ in range(8):
            lat = float(rng.uniform(-4.7, -1.5))
            lon = float(rng.uniform(39.5, 43.5))
            rows.append(
                dict(
                    effort_date=(base + pd.Timedelta(days=day)).strftime("%Y-%m-%d"),
                    lat=round(lat, 3),
                    lon=round(lon, 3),
                    hours=round(float(rng.uniform(0.5, 18.0)), 2),
                    vessel_count=int(rng.integers(1, 6)),
                    flag="UNK",
                    gear="trawlers",
                    source="demo_seed",
                )
            )
    demo = pd.DataFrame(rows)
    # Ensure table exists with flexible columns
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fact_gfw_fishing_effort (
                    effort_date VARCHAR,
                    lat DOUBLE PRECISION,
                    lon DOUBLE PRECISION,
                    hours DOUBLE PRECISION,
                    vessel_count INTEGER,
                    flag VARCHAR,
                    gear VARCHAR,
                    source VARCHAR
                )
                """
            )
        )
        conn.execute(text("DELETE FROM fact_gfw_fishing_effort"))
        demo.to_sql("fact_gfw_fishing_effort", conn, if_exists="append", index=False, method="multi")
    logger.info("Demo GFW rows: %s", len(demo))
    return load_gfw(eng)


def run():
    logger.info("=== Phase 15 fisheries intelligence ===")
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    from init_phase15_fisheries import main as ensure_schema

    ensure_schema()
    eng = engine()

    gfw = seed_demo_gfw_if_empty(eng)
    logger.info("GFW rows: %s hours=%.1f", len(gfw), float(gfw["hours"].sum()) if not gfw.empty else 0)

    grid = build_effort_grid(gfw, now)
    write(eng, "fact_fishing_effort_grid", grid)

    hotspots = build_hotspots(grid, now)
    write(eng, "fact_fishing_hotspots", hotspots)

    season = build_seasonality(gfw, now)
    write(eng, "fact_fisheries_seasonality", season)

    risk = build_risk(eng, gfw, hotspots, now)
    write(eng, "fact_illegal_fishing_risk", risk)

    alerts = build_alerts(risk, hotspots, now)
    write(eng, "fact_fisheries_alerts", alerts)

    if not risk.empty:
        logger.info(
            "Risk: level=%s score=%s conf=%s",
            risk.iloc[0]["risk_level"],
            risk.iloc[0]["risk_score"],
            risk.iloc[0]["confidence_score"],
        )
    logger.info(
        "Done: grid=%s hotspots=%s season=%s alerts=%s",
        len(grid),
        len(hotspots),
        len(season),
        len(alerts),
    )
    logger.info("=== Phase 15 complete ===")
    eng.dispose()


if __name__ == "__main__":
    run()

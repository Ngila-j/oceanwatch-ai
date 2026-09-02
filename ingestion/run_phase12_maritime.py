"""
Phase 12 complete — vessel profiles, tracks, geofences, behaviour (Kenya).
Uses fact_ais_positions (+ optional fact_vessel_anomalies).
Writes dim_vessels_maritime (not legacy dim_vessels).
"""

import logging
import random
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase12_maritime_v1.0"
REGION = "kenya_eez"
MIN_LAT, MAX_LAT = -6.0, 3.0
MIN_LON, MAX_LON = 38.0, 46.0
MOMBASA = (-4.05, 39.67)


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


def write(con, table, df, replace=True):
    if df is None or df.empty:
        logger.info("%s: 0 rows", table)
        return
    use = [c for c in df.columns if c in cols(con, table)]
    if not use:
        logger.warning("No columns for %s", table)
        return
    if replace:
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


def in_box(lat, lon, min_lat, max_lat, min_lon, max_lon):
    return (lat >= min_lat) & (lat <= max_lat) & (lon >= min_lon) & (lon <= max_lon)


def load_ais(con):
    df = qdf(
        con,
        """
        SELECT *
        FROM pg.public.fact_ais_positions
        ORDER BY event_time
        """,
    )
    if df.empty:
        return df
    rename = {}
    for a, b in [
        ("lat", "latitude"),
        ("lon", "longitude"),
        ("speed", "sog"),
        ("course", "cog"),
        ("heading", "cog"),
        ("ship_name", "vessel_name"),
        ("name", "vessel_name"),
    ]:
        if a in df.columns and b not in df.columns:
            rename[a] = b
    if rename:
        df = df.rename(columns=rename)
    if "mmsi" not in df.columns:
        logger.error("AIS missing mmsi")
        return pd.DataFrame()
    df["mmsi"] = df["mmsi"].astype(str)
    if "latitude" not in df.columns or "longitude" not in df.columns:
        return pd.DataFrame()
    df["event_time"] = pd.to_datetime(df.get("event_time"), errors="coerce")
    df["sog"] = pd.to_numeric(df["sog"], errors="coerce") if "sog" in df.columns else np.nan
    df["cog"] = pd.to_numeric(df["cog"], errors="coerce") if "cog" in df.columns else np.nan
    if "vessel_name" not in df.columns:
        df["vessel_name"] = "UNKNOWN"
    if "vessel_type" not in df.columns:
        df["vessel_type"] = "UNKNOWN"
    if "source" not in df.columns:
        df["source"] = "UNKNOWN"
    df = df.dropna(subset=["latitude", "longitude", "event_time"])
    return df


def build_dim_vessels(ais: pd.DataFrame, now):
    if ais.empty:
        return pd.DataFrame()
    g = ais.groupby("mmsi", as_index=False).agg(
        vessel_name=("vessel_name", "last"),
        vessel_type=("vessel_type", "last"),
        first_seen=("event_time", "min"),
        last_seen=("event_time", "max"),
        source=("source", "last"),
    )
    g["flag"] = None
    g["updated_at"] = now
    return g


def build_track_points(ais: pd.DataFrame):
    if ais.empty:
        return pd.DataFrame()
    out = ais[["mmsi", "event_time", "latitude", "longitude"]].copy()
    out["sog"] = ais["sog"] if "sog" in ais.columns else np.nan
    out["cog"] = ais["cog"] if "cog" in ais.columns else np.nan
    out["source"] = ais["source"] if "source" in ais.columns else "UNKNOWN"
    out["in_kenya_box"] = in_box(
        out["latitude"], out["longitude"], MIN_LAT, MAX_LAT, MIN_LON, MAX_LON
    )
    out["near_mombasa"] = (
        ((out["latitude"] - MOMBASA[0]).abs() < 0.35)
        & ((out["longitude"] - MOMBASA[1]).abs() < 0.35)
    )
    return out


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p = np.radians(lat2 - lat1)
    q = np.radians(lon2 - lon1)
    a = (
        np.sin(p / 2) ** 2
        + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(q / 2) ** 2
    )
    return 2 * r * np.arcsin(np.sqrt(a))


def profile_one(g: pd.DataFrame, anomaly_map: dict, now):
    g = g.sort_values("event_time")
    mmsi = str(g["mmsi"].iloc[-1])
    name = str(g["vessel_name"].iloc[-1])
    vtype = str(g["vessel_type"].iloc[-1]) if "vessel_type" in g.columns else "UNKNOWN"
    last = g.iloc[-1]
    n = len(g)
    hours = max(
        (g["event_time"].max() - g["event_time"].min()).total_seconds() / 3600.0, 0.01
    )
    sog = g["sog"].dropna() if "sog" in g.columns else pd.Series(dtype=float)
    speed_mean = float(sog.mean()) if len(sog) else 0.0
    speed_max = float(sog.max()) if len(sog) else 0.0
    low_ratio = float((sog < 2.0).mean()) if len(sog) else 0.0

    cog = g["cog"].dropna() if "cog" in g.columns else pd.Series(dtype=float)
    turn = float(cog.diff().abs().mean()) if len(cog) > 2 else 0.0

    if n >= 2:
        dist = haversine_km(
            g["latitude"].iloc[0],
            g["longitude"].iloc[0],
            g["latitude"].iloc[-1],
            g["longitude"].iloc[-1],
        )
        path = 0.0
        for i in range(1, n):
            path += haversine_km(
                g["latitude"].iloc[i - 1],
                g["longitude"].iloc[i - 1],
                g["latitude"].iloc[i],
                g["longitude"].iloc[i],
            )
        efficiency = float(dist / path) if path > 0.01 else 1.0
    else:
        efficiency = 1.0

    in_kenya = bool(
        in_box(last["latitude"], last["longitude"], MIN_LAT, MAX_LAT, MIN_LON, MAX_LON)
    )
    near = bool(
        abs(last["latitude"] - MOMBASA[0]) < 0.35
        and abs(last["longitude"] - MOMBASA[1]) < 0.35
    )
    mpa = bool(in_box(last["latitude"], last["longitude"], -3.50, -2.80, 40.00, 40.60))

    score = 0.0
    evidence = []
    if low_ratio > 0.4:
        score += 25
        evidence.append(f"low_speed_ratio={low_ratio:.2f}")
    if turn > 25:
        score += 20
        evidence.append(f"turn_proxy={turn:.1f}")
    if efficiency < 0.45 and n > 5:
        score += 20
        evidence.append(f"track_efficiency={efficiency:.2f}")
    if speed_max > 25:
        score += 10
        evidence.append(f"speed_max={speed_max:.1f}")
    if mpa:
        score += 15
        evidence.append("mpa_proxy_interaction")
    if near and low_ratio > 0.3:
        score += 10
        evidence.append("near_mombasa_low_speed")

    anom = anomaly_map.get(name) or anomaly_map.get(mmsi)
    risk = score
    conf = 70.0
    if anom:
        risk = max(risk, float(anom.get("risk_score") or 0))
        conf = float(anom.get("confidence_score") or conf)
        evidence.append("linked_vessel_anomaly")

    risk = min(100.0, risk)
    level = (
        "HIGH"
        if risk >= 75
        else "ELEVATED"
        if risk >= 50
        else "MONITOR"
        if risk >= 30
        else "LOW"
    )

    return dict(
        mmsi=mmsi,
        vessel_name=name,
        vessel_type=vtype,
        last_lat=float(last["latitude"]),
        last_lon=float(last["longitude"]),
        last_sog=float(last["sog"]) if pd.notna(last.get("sog")) else None,
        last_cog=float(last["cog"]) if pd.notna(last.get("cog")) else None,
        last_seen=last["event_time"].to_pydatetime()
        if hasattr(last["event_time"], "to_pydatetime")
        else last["event_time"],
        position_count=int(n),
        track_hours=round(hours, 2),
        speed_mean=round(speed_mean, 2),
        speed_max=round(speed_max, 2),
        low_speed_ratio=round(low_ratio, 3),
        turn_rate_proxy=round(turn, 2),
        track_efficiency=round(efficiency, 3),
        behaviour_score=round(score, 1),
        behaviour_level=level,
        risk_score=round(risk, 1),
        confidence_score=round(conf, 1),
        in_kenya_box=in_kenya,
        near_mombasa=near,
        mpa_interaction_flag=mpa,
        geofence_hits=0,
        evidence=" | ".join(evidence) if evidence else "nominal",
        model_version=MODEL,
        region_id=REGION,
        computed_at=now,
    )


def build_geofence_events(ais: pd.DataFrame, fences: pd.DataFrame, now):
    if ais.empty or fences.empty:
        return pd.DataFrame()
    rows = []
    for _, f in fences.iterrows():
        mask = in_box(
            ais["latitude"],
            ais["longitude"],
            float(f["min_lat"]),
            float(f["max_lat"]),
            float(f["min_lon"]),
            float(f["max_lon"]),
        )
        sub = ais.loc[mask]
        if sub.empty:
            continue
        for mmsi, g in sub.groupby("mmsi"):
            last = g.sort_values("event_time").iloc[-1]
            rows.append(
                dict(
                    event_id=random.randint(10_000_000, 99_999_999),
                    mmsi=str(mmsi),
                    vessel_name=str(last.get("vessel_name") or ""),
                    fence_id=f["fence_id"],
                    fence_name=f["fence_name"],
                    event_kind="INSIDE",
                    event_time=last["event_time"].to_pydatetime()
                    if hasattr(last["event_time"], "to_pydatetime")
                    else last["event_time"],
                    latitude=float(last["latitude"]),
                    longitude=float(last["longitude"]),
                    sog=float(last["sog"]) if pd.notna(last.get("sog")) else None,
                    region_id=REGION,
                    model_version=MODEL,
                    created_at=now,
                )
            )
    return pd.DataFrame(rows)


def run():
    logger.info("=== Phase 12 maritime intelligence ===")
    now = datetime.utcnow()
    con = connect()

    ais = load_ais(con)
    logger.info("AIS rows loaded: %s", len(ais))

    anom = qdf(con, "SELECT * FROM pg.public.fact_vessel_anomalies")
    anomaly_map = {}
    if not anom.empty:
        for _, r in anom.iterrows():
            key = str(r.get("vessel_name") or r.get("mmsi") or "")
            anomaly_map[key] = r.to_dict()

    dim = build_dim_vessels(ais, now)
    # Dedicated table — avoids legacy dim_vessels.vessel_key NOT NULL
    write(con, "dim_vessels_maritime", dim)

    tracks = build_track_points(ais)
    if len(tracks) > 5000:
        tracks = tracks.sort_values("event_time").tail(5000)
    write(con, "fact_vessel_track_points", tracks)

    profiles = []
    if not ais.empty:
        for mmsi, g in ais.groupby("mmsi"):
            profiles.append(profile_one(g, anomaly_map, now))
    prof_df = pd.DataFrame(profiles)

    fences = qdf(con, "SELECT * FROM pg.public.dim_geofences")
    ge = build_geofence_events(ais, fences, now)
    write(con, "fact_geofence_events", ge)

    if not prof_df.empty and not ge.empty:
        hits = ge.groupby("mmsi").size().to_dict()
        prof_df["geofence_hits"] = prof_df["mmsi"].map(lambda m: int(hits.get(m, 0)))
    write(con, "fact_vessel_profiles", prof_df)

    logger.info(
        "Vessels=%s profiles=%s tracks=%s geofence_events=%s",
        len(dim),
        len(prof_df),
        len(tracks),
        len(ge),
    )
    logger.info("=== Phase 12 complete ===")


if __name__ == "__main__":
    run()
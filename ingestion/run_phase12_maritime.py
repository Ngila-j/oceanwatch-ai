"""
Phase 12 — vessel profiles, tracks, geofences, behaviour (Kenya).
Uses fact_ais_positions (+ optional fact_vessel_anomalies).
Writes dim_vessels_maritime (not legacy dim_vessels).

SQLAlchemy + OCEANWATCH_DB_URI (Supabase-safe).
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from db_utils import get_db_uri

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase12_maritime_v1.1"
REGION = "kenya_eez"
MIN_LAT, MAX_LAT = -4.8, -1.5
MIN_LON, MAX_LON = 39.0, 44.0
MOMBASA = (-4.05, 39.67)


def sa_uri() -> str:
    uri = get_db_uri()
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


def engine():
    uri = sa_uri()
    logger.info("Phase 12 → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
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


def in_box(lat, lon, min_lat, max_lat, min_lon, max_lon) -> bool:
    try:
        return min_lat <= float(lat) <= max_lat and min_lon <= float(lon) <= max_lon
    except Exception:
        return False


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p = np.radians(lat2 - lat1)
    q = np.radians(lon2 - lon1)
    a = (
        np.sin(p / 2) ** 2
        + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(q / 2) ** 2
    )
    return float(2 * r * np.arcsin(np.sqrt(a)))


def normalize_ais(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
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
        logger.error("AIS missing lat/lon")
        return pd.DataFrame()
    if "event_time" not in df.columns:
        if "timestamp" in df.columns:
            df["event_time"] = pd.to_datetime(df["timestamp"], errors="coerce")
        else:
            df["event_time"] = pd.Timestamp.utcnow()
    else:
        df["event_time"] = pd.to_datetime(df["event_time"], errors="coerce")
    if "vessel_name" not in df.columns:
        df["vessel_name"] = df["mmsi"]
    if "vessel_type" not in df.columns:
        df["vessel_type"] = "UNKNOWN"
    if "sog" not in df.columns:
        df["sog"] = np.nan
    if "cog" not in df.columns:
        df["cog"] = np.nan
    if "source" not in df.columns:
        df["source"] = "UNKNOWN"
    df = df.dropna(subset=["latitude", "longitude", "event_time"])
    return df.sort_values(["mmsi", "event_time"]).reset_index(drop=True)


def synthetic_ais(now) -> pd.DataFrame:
    """Fallback demo fleet when fact_ais_positions is empty."""
    rng = np.random.default_rng(42)
    vessels = [
        ("625001001", "MV SAHARA STAR", "CARGO"),
        ("625001002", "FV PATE RUNNER", "FISHING"),
        ("625001003", "MT INDIAN TIDE", "TANKER"),
        ("625001004", "FV LAMU BREEZE", "FISHING"),
        ("625001005", "SV DHOW HORIZON", "OTHER"),
        ("625001006", "MV MOMBASA LINK", "CARGO"),
        ("625001007", "FV KIUNGA NET", "FISHING"),
        ("625001008", "MT REEF GUARD", "TANKER"),
    ]
    rows = []
    for mmsi, name, vtype in vessels:
        base_lat = float(rng.uniform(-4.5, -2.0))
        base_lon = float(rng.uniform(39.6, 42.5))
        sog0 = float(rng.uniform(0.5, 14.0))
        for h in range(24):
            t = now - timedelta(hours=23 - h)
            lat = base_lat + 0.02 * np.sin(h / 4) + float(rng.normal(0, 0.01))
            lon = base_lon + 0.03 * (h / 24) + float(rng.normal(0, 0.01))
            sog = max(0.0, sog0 + float(rng.normal(0, 1.5)))
            # Force a few low-speed / MPA-ish samples for demo behaviour
            if name.startswith("FV") and h % 5 == 0:
                sog = float(rng.uniform(0.1, 1.2))
            if name == "FV KIUNGA NET":
                lat = -3.1 + 0.05 * np.sin(h / 3)
                lon = 40.3 + 0.04 * np.cos(h / 3)
            rows.append(
                dict(
                    mmsi=mmsi,
                    vessel_name=name,
                    vessel_type=vtype,
                    latitude=lat,
                    longitude=lon,
                    sog=sog,
                    cog=float(rng.uniform(0, 360)),
                    event_time=t,
                    source="DEMO_PHASE12",
                )
            )
    return pd.DataFrame(rows)


def load_ais(eng) -> pd.DataFrame:
    df = qdf(
        eng,
        """
        SELECT *
        FROM fact_ais_positions
        ORDER BY event_time DESC NULLS LAST
        LIMIT 5000
        """,
    )
    df = normalize_ais(df)
    if df.empty:
        logger.warning("No AIS rows — seeding synthetic demo fleet")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        df = synthetic_ais(now)
    return df


def build_dim_vessels(ais: pd.DataFrame, now) -> pd.DataFrame:
    if ais.empty:
        return pd.DataFrame()
    g = ais.groupby("mmsi", as_index=False).agg(
        vessel_name=("vessel_name", "last"),
        vessel_type=("vessel_type", "last"),
        first_seen=("event_time", "min"),
        last_seen=("event_time", "max"),
        position_count=("event_time", "count"),
        source=("source", "last"),
    )
    g["flag"] = None
    g["updated_at"] = now
    return g


def profile_one(mmsi, g: pd.DataFrame, anomaly_map: dict, now) -> dict:
    g = g.sort_values("event_time")
    last = g.iloc[-1]
    n = len(g)
    name = str(last.get("vessel_name") or mmsi)
    vtype = str(last.get("vessel_type") or "UNKNOWN")

    hours = 0.0
    if n >= 2:
        hours = max(
            0.0,
            (g["event_time"].iloc[-1] - g["event_time"].iloc[0]).total_seconds() / 3600.0,
        )

    sog = pd.to_numeric(g.get("sog"), errors="coerce")
    speed_mean = float(sog.mean()) if sog.notna().any() else 0.0
    speed_max = float(sog.max()) if sog.notna().any() else 0.0
    low_ratio = float((sog.fillna(0) < 2.0).mean()) if n else 0.0

    turn = 0.0
    if "cog" in g.columns and n >= 3:
        cog = pd.to_numeric(g["cog"], errors="coerce").dropna()
        if len(cog) >= 3:
            d = np.abs(np.diff(cog.values))
            d = np.minimum(d, 360 - d)
            turn = float(np.mean(d))

    dist = haversine_km(
        g["latitude"].iloc[0],
        g["longitude"].iloc[0],
        g["latitude"].iloc[-1],
        g["longitude"].iloc[-1],
    )
    path = 0.0
    if n >= 2:
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

    anom = anomaly_map.get(name) or anomaly_map.get(str(mmsi))
    risk = score
    conf = 70.0
    if anom:
        risk = max(risk, float(anom.get("risk_score") or 0))
        conf = float(anom.get("confidence_score") or conf)
        evidence.append("linked_vessel_anomaly")

    risk = min(100.0, risk)
    if risk >= 75:
        level = "HIGH"
    elif risk >= 50:
        level = "ELEVATED"
    elif risk >= 30:
        level = "MONITOR"
    else:
        level = "LOW"

    last_seen = last["event_time"]
    if hasattr(last_seen, "to_pydatetime"):
        last_seen = last_seen.to_pydatetime()
    if getattr(last_seen, "tzinfo", None) is not None:
        last_seen = last_seen.replace(tzinfo=None)

    return dict(
        mmsi=str(mmsi),
        vessel_name=name,
        vessel_type=vtype,
        last_lat=float(last["latitude"]),
        last_lon=float(last["longitude"]),
        last_sog=float(last["sog"]) if pd.notna(last.get("sog")) else None,
        last_cog=float(last["cog"]) if pd.notna(last.get("cog")) else None,
        last_seen=last_seen,
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
        in_kenya_box=bool(in_kenya),
        near_mombasa=bool(near),
        mpa_interaction_flag=bool(mpa),
        geofence_hits=0,
        evidence=" | ".join(evidence) if evidence else "nominal",
        model_version=MODEL,
        region_id=REGION,
        computed_at=now,
    )


def build_profiles(ais: pd.DataFrame, anomaly_map: dict, now) -> pd.DataFrame:
    if ais.empty:
        return pd.DataFrame()
    rows = []
    for mmsi, g in ais.groupby("mmsi"):
        rows.append(profile_one(mmsi, g, anomaly_map, now))
    return pd.DataFrame(rows)


def build_tracks(ais: pd.DataFrame, now) -> pd.DataFrame:
    if ais.empty:
        return pd.DataFrame()
    # Keep last ~80 points per vessel for UI tracks
    parts = []
    for _, g in ais.groupby("mmsi"):
        parts.append(g.sort_values("event_time").tail(80))
    t = pd.concat(parts, ignore_index=True)
    out = pd.DataFrame(
        {
            "mmsi": t["mmsi"].astype(str),
            "event_time": pd.to_datetime(t["event_time"]).dt.tz_localize(None),
            "latitude": t["latitude"].astype(float),
            "longitude": t["longitude"].astype(float),
            "sog": pd.to_numeric(t.get("sog"), errors="coerce"),
            "cog": pd.to_numeric(t.get("cog"), errors="coerce"),
            "vessel_name": t.get("vessel_name"),
            "source": t.get("source"),
            "created_at": now,
        }
    )
    return out


def build_geofence_events(ais: pd.DataFrame, fences: pd.DataFrame, now) -> pd.DataFrame:
    if ais.empty or fences.empty:
        return pd.DataFrame()
    rows = []
    for _, f in fences.iterrows():
        mask = ais.apply(
            lambda r: in_box(
                r["latitude"],
                r["longitude"],
                float(f["min_lat"]),
                float(f["max_lat"]),
                float(f["min_lon"]),
                float(f["max_lon"]),
            ),
            axis=1,
        )
        sub = ais.loc[mask]
        if sub.empty:
            continue
        for mmsi, g in sub.groupby("mmsi"):
            last = g.sort_values("event_time").iloc[-1]
            et = last["event_time"]
            if hasattr(et, "to_pydatetime"):
                et = et.to_pydatetime()
            if getattr(et, "tzinfo", None) is not None:
                et = et.replace(tzinfo=None)
            rows.append(
                dict(
                    event_id=random.randint(10_000_000, 99_999_999),
                    mmsi=str(mmsi),
                    vessel_name=str(last.get("vessel_name") or ""),
                    fence_id=str(f.get("fence_id")),
                    fence_name=str(f.get("fence_name")),
                    event_time=et,
                    latitude=float(last["latitude"]),
                    longitude=float(last["longitude"]),
                    sog=float(last["sog"]) if pd.notna(last.get("sog")) else None,
                    region_id=REGION,
                    model_version=MODEL,
                    created_at=now,
                )
            )
    return pd.DataFrame(rows)


def attach_geofence_hits(profiles: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if profiles is None or profiles.empty:
        return profiles
    p = profiles.copy()
    if events is None or events.empty:
        p["geofence_hits"] = 0
        return p
    hits = events.groupby("mmsi").size().rename("geofence_hits")
    p = p.drop(columns=["geofence_hits"], errors="ignore")
    p = p.merge(hits, left_on="mmsi", right_index=True, how="left")
    p["geofence_hits"] = p["geofence_hits"].fillna(0).astype(int)
    return p


def load_anomaly_map(eng) -> dict:
    df = qdf(
        eng,
        """
        SELECT * FROM fact_vessel_anomalies
        ORDER BY created_at DESC NULLS LAST
        LIMIT 500
        """,
    )
    if df.empty:
        return {}
    out = {}
    for _, r in df.iterrows():
        key = str(r.get("vessel_name") or r.get("mmsi") or "")
        if not key:
            continue
        out[key] = {
            "risk_score": r.get("risk_score") or r.get("anomaly_score") or 0,
            "confidence_score": r.get("confidence_score") or 70,
        }
    return out


def run():
    logger.info("=== Phase 12 maritime intelligence ===")
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    from init_phase12_maritime import main as ensure_schema

    ensure_schema()
    eng = engine()

    ais = load_ais(eng)
    logger.info("AIS rows loaded: %s vessels=%s", len(ais), ais["mmsi"].nunique() if not ais.empty else 0)

    anomaly_map = load_anomaly_map(eng)
    logger.info("Anomaly map keys: %s", len(anomaly_map))

    dim = build_dim_vessels(ais, now)
    write(eng, "dim_vessels_maritime", dim)

    profiles = build_profiles(ais, anomaly_map, now)
    fences = qdf(eng, "SELECT * FROM dim_geofences")
    events = build_geofence_events(ais, fences, now)
    profiles = attach_geofence_hits(profiles, events)
    write(eng, "fact_vessel_profiles", profiles)

    tracks = build_tracks(ais, now)
    write(eng, "fact_vessel_track_points", tracks)
    write(eng, "fact_geofence_events", events)

    if not profiles.empty:
        logger.info(
            "Profiles=%s elevated+=%s mpa=%s near_msa=%s",
            len(profiles),
            int((profiles["risk_score"] >= 50).sum()),
            int(profiles["mpa_interaction_flag"].fillna(False).sum()),
            int(profiles["near_mombasa"].fillna(False).sum()),
        )
    logger.info("Tracks=%s geofence_events=%s", len(tracks), len(events))
    logger.info("=== Phase 12 complete ===")
    eng.dispose()


if __name__ == "__main__":
    run()

"""
Phase 19 — Maritime event engine.
Vessel state, movements, and events from AIS + profiles + geofences.
Patterns for human review only — not proof of illegal activity.

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

MODEL = "phase19_events_v1.1"
REGION = "kenya_eez"
COUNTRY = "KE"
DISCLAIMER = "OceanWatch flags patterns for review; an event is not proof of illegal activity."


def sa_uri() -> str:
    uri = get_db_uri()
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


def engine():
    uri = sa_uri()
    logger.info("Phase 19 → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
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


def _ts(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    t = pd.to_datetime(v, errors="coerce")
    if pd.isna(t):
        return None
    if hasattr(t, "to_pydatetime"):
        t = t.to_pydatetime()
    if getattr(t, "tzinfo", None) is not None:
        t = t.replace(tzinfo=None)
    return t


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p = np.radians(lat2 - lat1)
    q = np.radians(lon2 - lon1)
    a = (
        np.sin(p / 2) ** 2
        + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(q / 2) ** 2
    )
    return float(2 * r * np.arcsin(np.sqrt(min(1.0, a))))


def normalize_ais(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rename = {}
    for a, b in [
        ("latitude", "lat"),
        ("longitude", "lon"),
        ("event_time", "timestamp"),
        ("ship_name", "vessel_name"),
        ("name", "vessel_name"),
    ]:
        if a in df.columns and b not in df.columns:
            rename[a] = b
    if rename:
        df = df.rename(columns=rename)
    if "mmsi" not in df.columns:
        return pd.DataFrame()
    df["mmsi"] = df["mmsi"].astype(str)
    for c in ("lat", "lon", "sog", "cog"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "timestamp" not in df.columns:
        if "ts" in df.columns:
            df["timestamp"] = pd.to_datetime(df["ts"], errors="coerce")
        else:
            df["timestamp"] = pd.Timestamp.utcnow()
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if "vessel_name" not in df.columns:
        df["vessel_name"] = df["mmsi"]
    if "vessel_type" not in df.columns:
        df["vessel_type"] = "UNKNOWN"
    if "source" not in df.columns:
        df["source"] = "AIS"
    df = df.dropna(subset=["lat", "lon", "timestamp"])
    return df.sort_values(["mmsi", "timestamp"]).reset_index(drop=True)


def build_movements(ais: pd.DataFrame, now) -> pd.DataFrame:
    if ais.empty or "mmsi" not in ais.columns:
        return pd.DataFrame()
    rows = []
    for mmsi, g in ais.groupby("mmsi"):
        g = g.sort_values("timestamp")
        n = len(g)
        sog = pd.to_numeric(g.get("sog"), errors="coerce")
        dist = 0.0
        if n >= 2:
            for i in range(1, n):
                dist += haversine_km(
                    g["lat"].iloc[i - 1],
                    g["lon"].iloc[i - 1],
                    g["lat"].iloc[i],
                    g["lon"].iloc[i],
                )
            hours = max(
                0.0,
                (g["timestamp"].iloc[-1] - g["timestamp"].iloc[0]).total_seconds() / 3600.0,
            )
        else:
            hours = 0.0
        rows.append(
            dict(
                mmsi=str(mmsi),
                vessel_name=str(g["vessel_name"].iloc[-1]),
                positions_count=int(n),
                avg_sog=round(float(sog.mean()), 2) if sog.notna().any() else None,
                max_sog=round(float(sog.max()), 2) if sog.notna().any() else None,
                min_sog=round(float(sog.min()), 2) if sog.notna().any() else None,
                track_hours=round(hours, 2),
                distance_km=round(dist, 2),
                start_time=_ts(g["timestamp"].iloc[0]),
                end_time=_ts(g["timestamp"].iloc[-1]),
                region_id=REGION,
                country_id=COUNTRY,
                model_version=MODEL,
                created_at=now,
            )
        )
    return pd.DataFrame(rows)


def build_state_and_events(profiles: pd.DataFrame, ais: pd.DataFrame, ge: pd.DataFrame, movements: pd.DataFrame, now):
    states = []
    events = []

    def _evt(mmsi, vessel_name, event_type, event_time, lat, lon, severity, confidence, evidence):
        return dict(
            event_id=random.randint(10_000_000, 99_999_999),
            mmsi=str(mmsi),
            vessel_name=vessel_name,
            event_type=event_type,
            event_time=_ts(event_time) or now,
            latitude=float(lat) if lat is not None and pd.notna(lat) else None,
            longitude=float(lon) if lon is not None and pd.notna(lon) else None,
            severity=severity,
            confidence=float(confidence),
            evidence=str(evidence)[:500],
            region_id=REGION,
            country_id=COUNTRY,
            model_version=MODEL,
            created_at=now,
        )

    if profiles is not None and not profiles.empty:
        for _, p in profiles.iterrows():
            mmsi = str(p.get("mmsi"))
            low = float(p.get("low_speed_ratio") or 0)
            loiter = low > 0.4
            near = bool(p.get("near_mombasa"))
            mpa = bool(p.get("mpa_interaction_flag"))
            sog = p.get("last_sog")
            try:
                sog_f = float(sog) if sog is not None and str(sog) != "nan" else None
            except Exception:
                sog_f = None

            if loiter:
                label = "LOITERING"
            elif sog_f is not None and sog_f < 0.5:
                label = "ANCHORED"
            else:
                label = "UNDERWAY"

            risk = float(p.get("risk_score") or p.get("behaviour_score") or 0)
            states.append(
                dict(
                    mmsi=mmsi,
                    vessel_name=p.get("vessel_name"),
                    vessel_type=p.get("vessel_type"),
                    last_lat=p.get("last_lat"),
                    last_lon=p.get("last_lon"),
                    last_sog=sog_f,
                    last_cog=p.get("last_cog"),
                    last_seen=_ts(p.get("last_seen")),
                    state_label=label,
                    loitering_flag=bool(loiter),
                    near_port_flag=bool(near),
                    mpa_flag=bool(mpa),
                    risk_score=risk,
                    source="fact_vessel_profiles",
                    region_id=REGION,
                    country_id=COUNTRY,
                    model_version=MODEL,
                    updated_at=now,
                )
            )

            if loiter:
                events.append(
                    _evt(
                        mmsi,
                        p.get("vessel_name"),
                        "PROLONGED_LOITERING",
                        p.get("last_seen"),
                        p.get("last_lat"),
                        p.get("last_lon"),
                        "MEDIUM" if risk < 70 else "HIGH",
                        float(p.get("confidence_score") or 70),
                        f"low_speed_ratio={low:.2f} | {DISCLAIMER}",
                    )
                )
            if near:
                events.append(
                    _evt(
                        mmsi,
                        p.get("vessel_name"),
                        "NEAR_PORT_WATCH",
                        p.get("last_seen"),
                        p.get("last_lat"),
                        p.get("last_lon"),
                        "LOW",
                        65.0,
                        f"near_mombasa | {DISCLAIMER}",
                    )
                )
            if mpa:
                events.append(
                    _evt(
                        mmsi,
                        p.get("vessel_name"),
                        "MPA_PROXY_INTERACTION",
                        p.get("last_seen"),
                        p.get("last_lat"),
                        p.get("last_lon"),
                        "MEDIUM",
                        60.0,
                        f"demo MPA proxy fence | {DISCLAIMER}",
                    )
                )

    # Movements-based unusual speed
    if movements is not None and not movements.empty:
        for _, m in movements.iterrows():
            if m.get("max_sog") is not None and float(m["max_sog"]) >= 25:
                events.append(
                    _evt(
                        m["mmsi"],
                        m.get("vessel_name"),
                        "UNUSUAL_SPEED",
                        m.get("end_time"),
                        None,
                        None,
                        "MEDIUM",
                        55.0,
                        f"max_sog={m['max_sog']} | {DISCLAIMER}",
                    )
                )

    # Geofence events
    if ge is not None and not ge.empty:
        for _, g in ge.iterrows():
            events.append(
                _evt(
                    g.get("mmsi"),
                    g.get("vessel_name"),
                    "GEOFENCE_HIT",
                    g.get("event_time"),
                    g.get("latitude"),
                    g.get("longitude"),
                    "LOW",
                    70.0,
                    f"fence={g.get('fence_name') or g.get('fence_id')} | {DISCLAIMER}",
                )
            )

    # Fallback state from AIS if no profiles
    if not states and ais is not None and not ais.empty and "mmsi" in ais.columns:
        for mmsi, g in ais.groupby("mmsi"):
            g2 = g.sort_values("timestamp")
            last = g2.iloc[-1]
            sog_f = float(last["sog"]) if pd.notna(last.get("sog")) else None
            label = "ANCHORED" if sog_f is not None and sog_f < 0.5 else "UNDERWAY"
            states.append(
                dict(
                    mmsi=str(mmsi),
                    vessel_name=last.get("vessel_name"),
                    vessel_type=last.get("vessel_type"),
                    last_lat=float(last["lat"]),
                    last_lon=float(last["lon"]),
                    last_sog=sog_f,
                    last_cog=float(last["cog"]) if pd.notna(last.get("cog")) else None,
                    last_seen=_ts(last["timestamp"]),
                    state_label=label,
                    loitering_flag=False,
                    near_port_flag=False,
                    mpa_flag=False,
                    risk_score=0.0,
                    source="fact_ais_positions",
                    region_id=REGION,
                    country_id=COUNTRY,
                    model_version=MODEL,
                    updated_at=now,
                )
            )

    return pd.DataFrame(states), pd.DataFrame(events)


def run():
    logger.info("=== Phase 19 maritime events ===")
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    from init_phase19_maritime import main as ensure_schema

    ensure_schema()
    eng = engine()

    ais = normalize_ais(qdf(eng, "SELECT * FROM fact_ais_positions ORDER BY event_time DESC NULLS LAST LIMIT 5000"))
    logger.info("AIS rows: %s", len(ais))

    profiles = qdf(eng, "SELECT * FROM fact_vessel_profiles")
    logger.info("Profiles: %s", len(profiles))

    ge = qdf(eng, "SELECT * FROM fact_geofence_events")
    logger.info("Geofence events in: %s", len(ge))

    movements = build_movements(ais, now)
    write(eng, "fact_vessel_movements", movements)

    states, events = build_state_and_events(profiles, ais, ge, movements, now)
    write(eng, "fact_vessel_state", states)
    write(eng, "fact_vessel_events", events)

    if not events.empty and "event_type" in events.columns:
        logger.info("Event types:\n%s", events["event_type"].value_counts().to_string())
    logger.info(
        "Done: state=%s events=%s moves=%s",
        len(states),
        len(events),
        len(movements),
    )
    logger.info("=== Phase 19 complete ===")
    eng.dispose()


if __name__ == "__main__":
    run()

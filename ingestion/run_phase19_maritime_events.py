"""
Phase 19 complete — Maritime event engine.
Vessel state, movements, and events from AIS + profiles + geofences.
Patterns for human review only — not proof of illegal activity.
"""

import logging
import random
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase19_events_v1.0"
REGION = "kenya_eez"
COUNTRY = "KE"
DISCLAIMER = "OceanWatch flags patterns for review; an event is not proof of illegal activity."


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


def qdf(con, sql):
    try:
        return con.execute(sql).fetchdf()
    except Exception as e:
        logger.warning("Query failed: %s", e)
        return pd.DataFrame()


def normalize_ais(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    rename = {}
    if "latitude" in df.columns and "lat" not in df.columns:
        rename["latitude"] = "lat"
    if "longitude" in df.columns and "lon" not in df.columns:
        rename["longitude"] = "lon"
    if "sog" in df.columns and "speed" not in df.columns:
        pass
    df = df.rename(columns=rename)
    if "mmsi" in df.columns:
        df["mmsi"] = df["mmsi"].astype(str)
    for c in ("lat", "lon", "sog", "cog"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    elif "ts" in df.columns:
        df["timestamp"] = pd.to_datetime(df["ts"], errors="coerce")
    return df


def build_movements(ais: pd.DataFrame, now) -> pd.DataFrame:
    if ais.empty or "mmsi" not in ais.columns:
        return pd.DataFrame()
    rows = []
    for mmsi, g in ais.groupby("mmsi"):
        sog = pd.to_numeric(g.get("sog"), errors="coerce") if "sog" in g.columns else pd.Series(dtype=float)
        ts = g["timestamp"] if "timestamp" in g.columns else None
        name = None
        if "vessel_name" in g.columns:
            name = g["vessel_name"].dropna().astype(str).iloc[0] if g["vessel_name"].notna().any() else None
        elif "shipname" in g.columns:
            name = g["shipname"].dropna().astype(str).iloc[0] if g["shipname"].notna().any() else None
        rows.append(
            dict(
                mmsi=str(mmsi),
                vessel_name=name,
                positions_count=int(len(g)),
                avg_sog=float(sog.mean()) if len(sog.dropna()) else None,
                max_sog=float(sog.max()) if len(sog.dropna()) else None,
                min_sog=float(sog.min()) if len(sog.dropna()) else None,
                first_seen=ts.min() if ts is not None else None,
                last_seen=ts.max() if ts is not None else None,
                region_id=REGION,
                model_version=MODEL,
                created_at=now,
            )
        )
    return pd.DataFrame(rows)


def build_state_and_events(con, ais, prof, ge, movements, now):
    states, events = [], []

    # Prefer profiles when available
    if not prof.empty:
        for _, p in prof.iterrows():
            mmsi = str(p.get("mmsi"))
            sog = p.get("last_sog")
            try:
                sog_f = float(sog) if sog is not None and str(sog) != "nan" else None
            except Exception:
                sog_f = None
            low = float(p.get("low_speed_ratio") or 0)
            loiter = low > 0.4
            near = bool(p.get("near_mombasa"))
            if near:
                label = "PORT_APPROACH"
            elif sog_f is not None and sog_f < 0.5:
                label = "STATIONARY"
            elif loiter:
                label = "LOITERING"
            else:
                label = "UNDERWAY"

            states.append(
                dict(
                    mmsi=mmsi,
                    vessel_name=p.get("vessel_name"),
                    vessel_type=p.get("vessel_type"),
                    last_lat=p.get("last_lat"),
                    last_lon=p.get("last_lon"),
                    last_sog=sog_f,
                    last_cog=p.get("last_cog"),
                    last_seen=p.get("last_seen"),
                    state_label=label,
                    in_port_approach=near,
                    loitering_flag=loiter,
                    region_id=REGION,
                    country_id=COUNTRY,
                    source=p.get("source") or "PROFILE",
                    model_version=MODEL,
                    updated_at=now,
                )
            )

            if loiter:
                events.append(
                    dict(
                        event_id=random.randint(10_000_000, 99_999_999),
                        mmsi=mmsi,
                        vessel_name=p.get("vessel_name"),
                        event_type="PROLONGED_LOITERING",
                        event_time=p.get("last_seen") or now,
                        lat=p.get("last_lat"),
                        lon=p.get("last_lon"),
                        severity="WATCH",
                        evidence=f"low_speed_ratio={low} | {DISCLAIMER}",
                        region_id=REGION,
                        country_id=COUNTRY,
                        model_version=MODEL,
                        created_at=now,
                    )
                )
            if near:
                events.append(
                    dict(
                        event_id=random.randint(10_000_000, 99_999_999),
                        mmsi=mmsi,
                        vessel_name=p.get("vessel_name"),
                        event_type="PORT_APPROACH",
                        event_time=p.get("last_seen") or now,
                        lat=p.get("last_lat"),
                        lon=p.get("last_lon"),
                        severity="INFO",
                        evidence="near_mombasa flag from vessel profile",
                        region_id="mombasa",
                        country_id=COUNTRY,
                        model_version=MODEL,
                        created_at=now,
                    )
                )
            try:
                bscore = float(p.get("behaviour_score") or 0)
            except Exception:
                bscore = 0.0
            if bscore >= 60:
                events.append(
                    dict(
                        event_id=random.randint(10_000_000, 99_999_999),
                        mmsi=mmsi,
                        vessel_name=p.get("vessel_name"),
                        event_type="BEHAVIOUR_FLAG",
                        event_time=p.get("last_seen") or now,
                        lat=p.get("last_lat"),
                        lon=p.get("last_lon"),
                        severity=str(p.get("behaviour_level") or "WATCH"),
                        evidence=str(p.get("evidence") or DISCLAIMER)[:300],
                        region_id=REGION,
                        country_id=COUNTRY,
                        model_version=MODEL,
                        created_at=now,
                    )
                )
            try:
                te = float(p.get("track_efficiency") or 1)
            except Exception:
                te = 1.0
            if te < 0.35:
                events.append(
                    dict(
                        event_id=random.randint(10_000_000, 99_999_999),
                        mmsi=mmsi,
                        vessel_name=p.get("vessel_name"),
                        event_type="ROUTE_INEFFICIENCY",
                        event_time=p.get("last_seen") or now,
                        lat=p.get("last_lat"),
                        lon=p.get("last_lon"),
                        severity="INFO",
                        evidence=f"track_efficiency={te}",
                        region_id=REGION,
                        country_id=COUNTRY,
                        model_version=MODEL,
                        created_at=now,
                    )
                )

    # Movements-based unusual speed
    if movements is not None and not movements.empty:
        for _, m in movements.iterrows():
            if m.get("max_sog") is not None and float(m["max_sog"]) >= 25:
                events.append(
                    dict(
                        event_id=random.randint(10_000_000, 99_999_999),
                        mmsi=str(m.get("mmsi")),
                        vessel_name=m.get("vessel_name"),
                        event_type="HIGH_SPEED",
                        event_time=m.get("last_seen") or now,
                        lat=None,
                        lon=None,
                        severity="INFO",
                        evidence=f"max_sog={m.get('max_sog')}",
                        region_id=REGION,
                        country_id=COUNTRY,
                        model_version=MODEL,
                        created_at=now,
                    )
                )

    # Geofence events
    if not ge.empty:
        for _, g in ge.iterrows():
            events.append(
                dict(
                    event_id=random.randint(10_000_000, 99_999_999),
                    mmsi=str(g.get("mmsi")),
                    vessel_name=g.get("vessel_name"),
                    event_type="GEOFENCE_INSIDE",
                    event_time=g.get("event_time") or now,
                    lat=g.get("latitude") if "latitude" in g else g.get("lat"),
                    lon=g.get("longitude") if "longitude" in g else g.get("lon"),
                    severity="INFO",
                    evidence=f"fence={g.get('fence_name') or g.get('fence_id')}",
                    region_id=REGION,
                    country_id=COUNTRY,
                    model_version=MODEL,
                    created_at=now,
                )
            )

    # If no profiles, derive crude state from latest AIS
    if not states and not ais.empty and "mmsi" in ais.columns:
        for mmsi, g in ais.groupby("mmsi"):
            g2 = g.sort_values("timestamp") if "timestamp" in g.columns else g
            last = g2.iloc[-1]
            sog_f = float(last["sog"]) if "sog" in last and pd.notna(last.get("sog")) else None
            label = "STATIONARY" if sog_f is not None and sog_f < 0.5 else "UNDERWAY"
            name = last.get("vessel_name") or last.get("shipname")
            states.append(
                dict(
                    mmsi=str(mmsi),
                    vessel_name=name,
                    vessel_type=last.get("vessel_type"),
                    last_lat=last.get("lat"),
                    last_lon=last.get("lon"),
                    last_sog=sog_f,
                    last_cog=last.get("cog"),
                    last_seen=last.get("timestamp"),
                    state_label=label,
                    in_port_approach=False,
                    loitering_flag=False,
                    region_id=REGION,
                    country_id=COUNTRY,
                    source=last.get("source") or "AIS",
                    model_version=MODEL,
                    updated_at=now,
                )
            )

    return pd.DataFrame(states), pd.DataFrame(events)


def run():
    logger.info("=== Phase 19 maritime events ===")
    now = datetime.utcnow()
    con = connect()

    ais = normalize_ais(qdf(con, "SELECT * FROM pg.public.fact_ais_positions"))
    prof = qdf(con, "SELECT * FROM pg.public.fact_vessel_profiles")
    ge = qdf(con, "SELECT * FROM pg.public.fact_geofence_events")
    logger.info("AIS=%s profiles=%s geofence_events=%s", len(ais), len(prof), len(ge))

    movements = build_movements(ais, now)
    write(con, "fact_vessel_movements", movements)

    states, events = build_state_and_events(con, ais, prof, ge, movements, now)
    write(con, "fact_vessel_state", states)
    write(con, "fact_vessel_events", events)

    logger.info(
        "States=%s events=%s movements=%s",
        len(states),
        len(events),
        len(movements),
    )
    logger.info("=== Phase 19 complete ===")


if __name__ == "__main__":
    run()
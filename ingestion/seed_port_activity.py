"""Seed Mombasa port activity + daily metrics (SQLAlchemy / Supabase-safe)."""

from __future__ import annotations

import logging
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, inspect, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PORT = "Mombasa"


def _load_env() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_db_uri() -> str:
    _load_env()
    try:
        from db_utils import get_db_uri as _g

        uri = _g()
    except Exception:  # noqa: BLE001
        uri = os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or ""
    if not uri:
        raise RuntimeError("OCEANWATCH_DB_URI / DATABASE_URL not set")
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


def _engine():
    uri = get_db_uri()
    args = {"connect_timeout": 20, "options": "-c statement_timeout=60000"}
    if "supabase" in uri.lower() or "pooler" in uri.lower():
        args["sslmode"] = "require"
    return create_engine(uri, pool_pre_ping=True, connect_args=args, pool_size=1, max_overflow=0)


def _cols(eng, table: str) -> set[str]:
    try:
        return {c["name"] for c in inspect(eng).get_columns(table, schema="public")}
    except Exception:  # noqa: BLE001
        return set()


def _insert_rows(conn, table: str, rows: list[dict], live_cols: set[str]) -> int:
    if not rows:
        return 0
    keys = [k for k in rows[0].keys() if not live_cols or k in live_cols]
    if not keys:
        return 0
    col_list = ", ".join(keys)
    placeholders = ", ".join(f":{k}" for k in keys)
    sql = text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})")
    # row-by-row is slower but more reliable on Supabase pooler than huge multi
    n = 0
    for r in rows:
        conn.execute(sql, {k: r[k] for k in keys})
        n += 1
    return n


def seed_port_activity() -> None:
    logger.info("=== Seed port activity / metrics ===")
    eng = _engine()

    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fact_port_activity (
                    event_time TIMESTAMP,
                    port_name VARCHAR,
                    event_type VARCHAR,
                    vessel_type VARCHAR,
                    flag VARCHAR,
                    mmsi BIGINT,
                    dwell_hours DOUBLE PRECISION
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fact_port_metrics (
                    metric_date DATE,
                    port_name VARCHAR,
                    arrivals INTEGER,
                    departures INTEGER,
                    active_vessels INTEGER,
                    container_vessels INTEGER,
                    tankers INTEGER,
                    fishing_vessels INTEGER,
                    avg_waiting_hours DOUBLE PRECISION,
                    congestion_index DOUBLE PRECISION,
                    congestion_level VARCHAR,
                    vs_30d_baseline_pct DOUBLE PRECISION,
                    unique_vessels INTEGER,
                    avg_dwell_hours DOUBLE PRECISION,
                    created_at TIMESTAMP
                )
                """
            )
        )
        # Ensure useful columns exist on older schemas
        for ddl in (
            "ALTER TABLE fact_port_metrics ADD COLUMN IF NOT EXISTS arrivals INTEGER",
            "ALTER TABLE fact_port_metrics ADD COLUMN IF NOT EXISTS departures INTEGER",
            "ALTER TABLE fact_port_metrics ADD COLUMN IF NOT EXISTS active_vessels INTEGER",
            "ALTER TABLE fact_port_metrics ADD COLUMN IF NOT EXISTS congestion_index DOUBLE PRECISION",
            "ALTER TABLE fact_port_metrics ADD COLUMN IF NOT EXISTS vs_30d_baseline_pct DOUBLE PRECISION",
            "ALTER TABLE fact_port_metrics ADD COLUMN IF NOT EXISTS avg_waiting_hours DOUBLE PRECISION",
            "ALTER TABLE fact_port_metrics ADD COLUMN IF NOT EXISTS avg_dwell_hours DOUBLE PRECISION",
            "ALTER TABLE fact_port_metrics ADD COLUMN IF NOT EXISTS unique_vessels INTEGER",
            "ALTER TABLE fact_port_metrics ADD COLUMN IF NOT EXISTS congestion_level VARCHAR",
            "ALTER TABLE fact_port_metrics ADD COLUMN IF NOT EXISTS created_at TIMESTAMP",
        ):
            try:
                conn.execute(text(ddl))
            except Exception:  # noqa: BLE001
                pass

    random.seed(42)
    vessel_types = ["CONTAINER", "TANKER", "BULK", "FISHING", "OTHER"]
    flags = ["Kenya", "Panama", "Liberia", "Singapore", "China", "India", "UAE"]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    base = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=13)

    # Keep activity small to avoid pooler timeouts
    activity_rows: list[dict] = []
    for day in range(14):
        for _ in range(6):
            event_time = base + timedelta(days=day, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            activity_rows.append(
                {
                    "event_time": event_time,
                    "port_name": PORT,
                    "event_type": random.choice(["ARRIVAL", "DEPARTURE"]),
                    "vessel_type": random.choice(vessel_types),
                    "flag": random.choice(flags),
                    "mmsi": random.randint(200_000_000, 799_999_999),
                    "dwell_hours": round(random.uniform(4.0, 36.0), 2),
                }
            )

    act = pd.DataFrame(activity_rows)
    act["day"] = pd.to_datetime(act["event_time"]).dt.date
    metric_rows: list[dict] = []
    for d, g in act.groupby("day"):
        arrivals = int((g["event_type"] == "ARRIVAL").sum())
        departures = int((g["event_type"] == "DEPARTURE").sum())
        active = int(g["mmsi"].nunique())
        containers = int((g["vessel_type"] == "CONTAINER").sum())
        tankers = int((g["vessel_type"] == "TANKER").sum())
        fishing = int((g["vessel_type"] == "FISHING").sum())
        avg_wait = float(g["dwell_hours"].mean())
        congestion = min(100.0, 15 + arrivals * 4.0 + avg_wait * 0.8 + active * 1.5)
        if congestion >= 70:
            level = "HIGH"
        elif congestion >= 45:
            level = "MODERATE"
        else:
            level = "LOW"
        metric_rows.append(
            {
                "metric_date": d,
                "port_name": PORT,
                "arrivals": arrivals,
                "departures": departures,
                "active_vessels": active,
                "container_vessels": containers,
                "tankers": tankers,
                "fishing_vessels": fishing,
                "avg_waiting_hours": round(avg_wait, 2),
                "congestion_index": round(congestion, 2),
                "congestion_level": level,
                "vs_30d_baseline_pct": round(random.uniform(-12.0, 22.0), 1),
                "unique_vessels": active,
                "avg_dwell_hours": round(avg_wait, 2),
                "vessel_count": active,
                "arrival_count": arrivals,
                "departure_count": departures,
                "created_at": now,
            }
        )

    act_cols = _cols(eng, "fact_port_activity")
    met_cols = _cols(eng, "fact_port_metrics")
    logger.info("activity cols=%s metrics cols=%s", sorted(act_cols)[:12], sorted(met_cols)[:12])

    with eng.begin() as conn:
        try:
            conn.execute(text("DELETE FROM fact_port_activity WHERE port_name = :p"), {"p": PORT})
        except Exception:  # noqa: BLE001
            conn.execute(text("DELETE FROM fact_port_activity"))
        n_act = _insert_rows(conn, "fact_port_activity", activity_rows, act_cols)
        logger.info("fact_port_activity inserted %s", n_act)

        try:
            conn.execute(text("DELETE FROM fact_port_metrics WHERE port_name = :p"), {"p": PORT})
        except Exception:  # noqa: BLE001
            conn.execute(text("DELETE FROM fact_port_metrics"))
        n_met = _insert_rows(conn, "fact_port_metrics", metric_rows, met_cols)
        logger.info("fact_port_metrics inserted %s", n_met)

    logger.info("=== Seed complete ===")
    eng.dispose()


if __name__ == "__main__":
    try:
        seed_port_activity()
    except Exception as e:  # noqa: BLE001
        logger.exception("seed_port_activity failed: %s", e)
        sys.exit(1)

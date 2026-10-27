"""Composite port operational risk: traffic + tide (+ baseline). SQLAlchemy / Supabase-safe."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
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


def _read(eng, sql: str) -> pd.DataFrame:
    try:
        return pd.read_sql(text(sql), eng)
    except Exception as e:  # noqa: BLE001
        logger.warning("query failed: %s", e)
        return pd.DataFrame()


def run() -> None:
    logger.info("=== Port Operational Risk ===")
    eng = _engine()

    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fact_port_risk (
                    risk_date DATE,
                    port_name VARCHAR,
                    traffic_score DOUBLE PRECISION,
                    tide_score DOUBLE PRECISION,
                    congestion_score DOUBLE PRECISION,
                    composite_risk DOUBLE PRECISION,
                    risk_level VARCHAR,
                    drivers VARCHAR,
                    created_at TIMESTAMP
                )
                """
            )
        )
        for ddl in (
            "ALTER TABLE fact_port_risk ADD COLUMN IF NOT EXISTS traffic_score DOUBLE PRECISION",
            "ALTER TABLE fact_port_risk ADD COLUMN IF NOT EXISTS tide_score DOUBLE PRECISION",
            "ALTER TABLE fact_port_risk ADD COLUMN IF NOT EXISTS congestion_score DOUBLE PRECISION",
            "ALTER TABLE fact_port_risk ADD COLUMN IF NOT EXISTS composite_risk DOUBLE PRECISION",
            "ALTER TABLE fact_port_risk ADD COLUMN IF NOT EXISTS risk_level VARCHAR",
            "ALTER TABLE fact_port_risk ADD COLUMN IF NOT EXISTS drivers VARCHAR",
            "ALTER TABLE fact_port_risk ADD COLUMN IF NOT EXISTS created_at TIMESTAMP",
            "ALTER TABLE fact_port_risk ADD COLUMN IF NOT EXISTS port_name VARCHAR",
        ):
            try:
                conn.execute(text(ddl))
            except Exception:  # noqa: BLE001
                pass

    metrics = _read(eng, "SELECT * FROM fact_port_metrics ORDER BY metric_date DESC LIMIT 5")
    activity = _read(
        eng,
        "SELECT * FROM fact_port_activity ORDER BY event_time DESC LIMIT 200",
    )
    tides = _read(eng, "SELECT * FROM stg_tides LIMIT 50")

    drivers: list[str] = []
    traffic_score = 40.0
    congestion_score = 40.0
    tide_score = 25.0

    def _num(series_or_row, *keys, default=0.0) -> float:
        for k in keys:
            try:
                if k in series_or_row.index:
                    v = series_or_row[k]
                else:
                    continue
            except Exception:  # noqa: BLE001
                continue
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            try:
                return float(v)
            except Exception:  # noqa: BLE001
                continue
        return float(default)

    if not metrics.empty:
        m = metrics.iloc[0]
        vessels = _num(m, "active_vessels", "vessel_count", "unique_vessels")
        arrivals = _num(m, "arrivals", "arrival_count")
        departures = _num(m, "departures", "departure_count")
        cong = _num(m, "congestion_index")
        avg_dwell = _num(m, "avg_waiting_hours", "avg_dwell_hours")
        baseline = _num(m, "vs_30d_baseline_pct")
        traffic_score = min(100.0, max(0.0, 35.0 + vessels * 3.0 + arrivals * 2.0 + baseline * 0.5))
        congestion_score = min(100.0, max(cong, avg_dwell * 2.0, vessels * 2.5, 30.0))
        drivers.append(
            f"vessels={int(vessels)} arrivals={int(arrivals)} departures={int(departures)} "
            f"cong={cong:.1f} wait={avg_dwell:.1f}h baseline={baseline:+.1f}%"
        )
    elif not activity.empty:
        n = len(activity)
        arrivals = int((activity.get("event_type", pd.Series(dtype=str)) == "ARRIVAL").sum())
        traffic_score = min(100.0, n * 1.5 + arrivals * 2.0)
        congestion_score = min(100.0, n * 1.2)
        drivers.append(f"activity_events={n} arrivals={arrivals}")
    else:
        drivers.append("no_metrics_or_activity")

    if not tides.empty:
        height_cols = [
            c
            for c in tides.columns
            if "height" in c.lower()
            or "level" in c.lower()
            or c.lower() in ("tide_m", "value", "water_level")
        ]
        tr = 0.0
        if height_cols:
            s = pd.to_numeric(tides[height_cols[0]], errors="coerce").dropna()
            if len(s) >= 2:
                tr = float(s.max() - s.min())
            elif len(s) == 1:
                tr = abs(float(s.iloc[0]))
        tide_score = min(100.0, max(0.0, tr * 25.0)) if tr else 25.0
        drivers.append(f"tide_range={tr:.2f}m")
    else:
        drivers.append("no_tide_data")

    composite = 0.45 * congestion_score + 0.30 * traffic_score + 0.25 * tide_score
    if composite >= 70:
        level = "HIGH"
    elif composite >= 45:
        level = "MODERATE"
    else:
        level = "LOW"

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = {
        "risk_date": now.date(),
        "port_name": PORT,
        "traffic_score": round(traffic_score, 1),
        "tide_score": round(tide_score, 1),
        "congestion_score": round(congestion_score, 1),
        "composite_risk": round(float(composite), 1),
        "risk_level": level,
        "drivers": " | ".join(drivers),
        "created_at": now,
    }

    live = _cols(eng, "fact_port_risk")
    use = [k for k in row if not live or k in live] or list(row.keys())
    payload = {k: row[k] for k in use}

    with eng.begin() as conn:
        try:
            conn.execute(
                text("DELETE FROM fact_port_risk WHERE risk_date = :d AND port_name = :p"),
                {"d": row["risk_date"], "p": PORT},
            )
        except Exception:  # noqa: BLE001
            conn.execute(text("DELETE FROM fact_port_risk WHERE risk_date = :d"), {"d": row["risk_date"]})
        col_list = ", ".join(use)
        placeholders = ", ".join(f":{c}" for c in use)
        conn.execute(text(f"INSERT INTO fact_port_risk ({col_list}) VALUES ({placeholders})"), payload)

    logger.info(
        "Port risk %s composite=%.1f traffic=%.1f tide=%.1f congestion=%.1f",
        level,
        composite,
        traffic_score,
        tide_score,
        congestion_score,
    )
    logger.info("=== Port risk complete ===")
    eng.dispose()


if __name__ == "__main__":
    try:
        run()
    except Exception as e:  # noqa: BLE001
        logger.exception("ml_port_risk failed: %s", e)
        sys.exit(1)

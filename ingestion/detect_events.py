"""
Kenya-first event detector.
Reads warehouse facts -> oceanwatch_events + risk_scores.
Does not invent legal findings.
"""

import logging
import random
from datetime import datetime

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL_VERSION = "event_detector_v0.1"
REGION = "kenya_eez"


def get_db_uri() -> str:
    import os

    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def connect():
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")
    return con


def table_columns(con, table: str):
    rows = con.execute(
        """
        SELECT column_name FROM pg.information_schema.columns
        WHERE table_schema='public' AND table_name=?
        """,
        [table],
    ).fetchall()
    return [r[0] for r in rows]


def write_df(con, table: str, df: pd.DataFrame):
    if df is None or df.empty:
        return
    cols = table_columns(con, table)
    use = [c for c in df.columns if c in cols]
    if not use:
        return
    con.register("tmp_ev", df[use])
    con.execute(f"INSERT INTO pg.public.{table} ({', '.join(use)}) SELECT {', '.join(use)} FROM tmp_ev")
    logger.info("Wrote %s rows -> %s", len(df), table)


def age_minutes(ts) -> float:
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return 9999.0
    try:
        t = pd.to_datetime(ts)
        if t.tzinfo is not None:
            t = t.tz_localize(None)
        return max(0.0, (datetime.utcnow() - t.to_pydatetime()).total_seconds() / 60.0)
    except Exception:
        return 9999.0


def conf_from_age(base: float, age_min: float) -> float:
    if age_min > 48 * 60:
        return max(20.0, base - 40)
    if age_min > 24 * 60:
        return max(30.0, base - 25)
    if age_min > 6 * 60:
        return max(40.0, base - 10)
    return base


def detect(con):
    now = datetime.utcnow()
    events = []
    risks = []

    # --- Port ---
    try:
        port = con.execute(
            """
            SELECT * FROM pg.public.fact_port_metrics
            ORDER BY metric_date DESC LIMIT 1
            """
        ).fetchdf()
    except Exception:
        port = pd.DataFrame()

    if not port.empty:
        p = port.iloc[0]
        age = age_minutes(p.get("metric_date"))
        level = str(p.get("congestion_level") or "").upper()
        idx = float(p.get("congestion_index") or 0)
        score = min(100.0, idx if idx else (80 if level == "HIGH" else 50 if level == "MODERATE" else 20))
        conf = conf_from_age(85.0, age)
        sev = "HIGH" if score >= 75 else "ELEVATED" if score >= 50 else "INFO"
        events.append(
            {
                "event_id": random.randint(10_000_000, 99_999_999),
                "event_type": "PORT_CONGESTION",
                "event_category": "PORT",
                "severity": sev,
                "event_time": now,
                "latitude": -4.05,
                "longitude": 39.67,
                "region_id": REGION,
                "entity_id": "mombasa",
                "confidence_score": round(conf, 1),
                "risk_score": round(score, 1),
                "model_version": MODEL_VERSION,
                "source": "fact_port_metrics",
                "title": f"Mombasa port congestion {level or 'UNKNOWN'}",
                "description": f"Congestion index={idx}, active_vessels={p.get('active_vessels')}",
                "evidence": f"metric_date={p.get('metric_date')}",
                "status": "OPEN",
                "created_at": now,
            }
        )
        risks.append(
            {
                "risk_id": random.randint(10_000_000, 99_999_999),
                "domain": "PORT",
                "entity_id": "mombasa",
                "region_id": REGION,
                "risk_score": round(score, 1),
                "confidence_score": round(conf, 1),
                "risk_level": sev,
                "reason": f"Congestion {level}, index {idx}",
                "data_freshness_minutes": round(age, 1),
                "model_version": MODEL_VERSION,
                "as_of_time": now,
                "created_at": now,
            }
        )

    # --- Vessel anomalies ---
    try:
        ves = con.execute(
            """
            SELECT * FROM pg.public.fact_vessel_anomalies
            WHERE risk_score >= 60
            ORDER BY risk_score DESC
            LIMIT 15
            """
        ).fetchdf()
    except Exception:
        ves = pd.DataFrame()

    for _, v in ves.iterrows():
        score = float(v.get("risk_score") or 0)
        conf = conf_from_age(float(v.get("confidence_score") or 60), 120)
        sev = "HIGH" if score >= 80 else "ELEVATED"
        events.append(
            {
                "event_id": random.randint(10_000_000, 99_999_999),
                "event_type": "VESSEL_BEHAVIOUR",
                "event_category": "MARITIME",
                "severity": sev,
                "event_time": now,
                "latitude": None,
                "longitude": None,
                "region_id": REGION,
                "entity_id": str(v.get("vessel_name") or v.get("mmsi") or "unknown"),
                "confidence_score": round(conf, 1),
                "risk_score": round(score, 1),
                "model_version": MODEL_VERSION,
                "source": "fact_vessel_anomalies",
                "title": f"Vessel behaviour flag — {v.get('vessel_name')}",
                "description": "Heuristic behaviour score for human review only.",
                "evidence": str(v.get("evidence") or ""),
                "status": "OPEN",
                "created_at": now,
            }
        )
        risks.append(
            {
                "risk_id": random.randint(10_000_000, 99_999_999),
                "domain": "VESSEL",
                "entity_id": str(v.get("vessel_name") or ""),
                "region_id": REGION,
                "risk_score": round(score, 1),
                "confidence_score": round(conf, 1),
                "risk_level": sev,
                "reason": str(v.get("evidence") or "Behaviour features"),
                "data_freshness_minutes": 120.0,
                "model_version": MODEL_VERSION,
                "as_of_time": now,
                "created_at": now,
            }
        )

    # --- Ocean / bloom ---
    try:
        bloom = con.execute(
            """
            SELECT * FROM pg.public.fact_bloom_risk
            ORDER BY risk_date DESC LIMIT 1
            """
        ).fetchdf()
    except Exception:
        bloom = pd.DataFrame()

    if not bloom.empty:
        b = bloom.iloc[0]
        prob = float(b.get("bloom_probability") or b.get("probability") or 0)
        age = age_minutes(b.get("risk_date") or b.get("created_at"))
        if prob >= 40:
            score = min(100.0, prob)
            conf = conf_from_age(80.0, age)
            sev = "ELEVATED" if score >= 50 else "INFO"
            events.append(
                {
                    "event_id": random.randint(10_000_000, 99_999_999),
                    "event_type": "BLOOM_RISK",
                    "event_category": "ENVIRONMENT",
                    "severity": sev,
                    "event_time": now,
                    "latitude": None,
                    "longitude": None,
                    "region_id": REGION,
                    "entity_id": "kenya_eez",
                    "confidence_score": round(conf, 1),
                    "risk_score": round(score, 1),
                    "model_version": MODEL_VERSION,
                    "source": "fact_bloom_risk",
                    "title": f"Bloom risk signal ({score:.0f})",
                    "description": str(b.get("drivers") or b.get("risk_level") or ""),
                    "evidence": f"prob={prob}",
                    "status": "OPEN",
                    "created_at": now,
                }
            )

    # --- SST mild anomaly vs recent mean ---
    try:
        sst = con.execute(
            """
            SELECT date_key, sst_celsius FROM pg.public.fact_ocean_conditions
            WHERE sst_celsius IS NOT NULL
            ORDER BY date_key DESC LIMIT 30
            """
        ).fetchdf()
    except Exception:
        sst = pd.DataFrame()

    if len(sst) >= 5:
        latest = float(sst.iloc[0]["sst_celsius"])
        mean = float(sst["sst_celsius"].mean())
        delta = latest - mean
        age = age_minutes(sst.iloc[0]["date_key"])
        if abs(delta) >= 0.3:
            score = min(100.0, 40 + abs(delta) * 40)
            conf = conf_from_age(75.0, age)
            events.append(
                {
                    "event_id": random.randint(10_000_000, 99_999_999),
                    "event_type": "SST_ANOMALY",
                    "event_category": "OCEAN",
                    "severity": "ELEVATED" if abs(delta) >= 0.5 else "INFO",
                    "event_time": now,
                    "latitude": None,
                    "longitude": None,
                    "region_id": REGION,
                    "entity_id": "kenya_eez",
                    "confidence_score": round(conf, 1),
                    "risk_score": round(score, 1),
                    "model_version": MODEL_VERSION,
                    "source": "fact_ocean_conditions",
                    "title": f"SST vs 30d sample mean {delta:+.2f} C",
                    "description": f"Latest {latest:.2f} C vs mean {mean:.2f} C",
                    "evidence": f"n={len(sst)}",
                    "status": "OPEN",
                    "created_at": now,
                }
            )
            risks.append(
                {
                    "risk_id": random.randint(10_000_000, 99_999_999),
                    "domain": "OCEAN",
                    "entity_id": "kenya_eez",
                    "region_id": REGION,
                    "risk_score": round(score, 1),
                    "confidence_score": round(conf, 1),
                    "risk_level": "ELEVATED" if abs(delta) >= 0.5 else "INFO",
                    "reason": f"SST delta {delta:+.2f} C vs recent mean",
                    "data_freshness_minutes": round(age, 1),
                    "model_version": MODEL_VERSION,
                    "as_of_time": now,
                    "created_at": now,
                }
            )

    return pd.DataFrame(events), pd.DataFrame(risks)


def run():
    logger.info("=== Event detector (Kenya) ===")
    con = connect()
    # clear same-day OPEN detector events to avoid runaway growth
    try:
        con.execute(
            """
            DELETE FROM pg.public.oceanwatch_events
            WHERE model_version = ?
              AND created_at::date = CURRENT_DATE
            """,
            [MODEL_VERSION],
        )
        con.execute(
            """
            DELETE FROM pg.public.risk_scores
            WHERE model_version = ?
              AND created_at::date = CURRENT_DATE
            """,
            [MODEL_VERSION],
        )
    except Exception as e:
        logger.warning("Cleanup skipped: %s", e)

    events, risks = detect(con)
    write_df(con, "oceanwatch_events", events)
    write_df(con, "risk_scores", risks)
    logger.info("Events=%s risks=%s", len(events), len(risks))
    logger.info("=== Event detector completed ===")


if __name__ == "__main__":
    run()
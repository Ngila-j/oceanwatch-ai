"""
Phase 16 complete — Operations & Platform.
System health checks, weekly report artifact, alert delivery log (dry-run).
"""

import logging
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase16_ops_v1.0"


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


def check_table(con, name, now):
    t0 = time.time()
    try:
        n = con.execute(f"SELECT COUNT(*) FROM pg.public.{name}").fetchone()[0]
        ms = (time.time() - t0) * 1000
        return dict(
            check_time=now,
            component=f"table:{name}",
            status="UP",
            detail=f"rows={n}",
            latency_ms=round(ms, 1),
            model_version=MODEL,
        )
    except Exception as e:
        return dict(
            check_time=now,
            component=f"table:{name}",
            status="DOWN",
            detail=str(e)[:200],
            latency_ms=None,
            model_version=MODEL,
        )


def build_health(con, now):
    critical = [
        "fact_ocean_conditions",
        "fact_alerts",
        "fact_port_metrics",
        "fact_gfw_fishing_effort",
        "fact_wio_intelligence_index",
        "fact_vessel_profiles",
        "fact_ocean_risk_fusion",
        "fact_port_ops_risk",
        "fact_illegal_fishing_risk",
    ]
    rows = []
    t0 = time.time()
    try:
        con.execute("SELECT 1").fetchone()
        rows.append(
            dict(
                check_time=now,
                component="postgres",
                status="UP",
                detail="SELECT 1 ok",
                latency_ms=round((time.time() - t0) * 1000, 1),
                model_version=MODEL,
            )
        )
    except Exception as e:
        rows.append(
            dict(
                check_time=now,
                component="postgres",
                status="DOWN",
                detail=str(e)[:200],
                latency_ms=None,
                model_version=MODEL,
            )
        )
    for t in critical:
        rows.append(check_table(con, t, now))
    return pd.DataFrame(rows)


def build_report(con, now):
    end = now.date()
    start = end - timedelta(days=7)
    lines = [
        f"OceanWatch Weekly Ops Brief — {start} → {end}",
        f"Generated: {now.isoformat()}Z",
        "",
    ]

    def one(sql, label):
        df = qdf(con, sql)
        if df.empty:
            lines.append(f"{label}: n/a")
            return
        lines.append(f"{label}: {df.iloc[0].to_dict()}")

    one(
        "SELECT overall_score, confidence_score FROM pg.public.fact_wio_intelligence_index ORDER BY index_date DESC LIMIT 1",
        "WIO-OII",
    )
    one(
        "SELECT composite_ocean_risk, risk_level FROM pg.public.fact_ocean_risk_fusion ORDER BY as_of_date DESC LIMIT 1",
        "Ocean composite",
    )
    one(
        "SELECT composite_ops_risk, risk_level FROM pg.public.fact_port_ops_risk ORDER BY as_of_date DESC LIMIT 1",
        "Port ops risk",
    )
    one(
        "SELECT risk_score, risk_level, gfw_hours FROM pg.public.fact_illegal_fishing_risk ORDER BY as_of_date DESC LIMIT 1",
        "Fisheries risk",
    )
    one(
        "SELECT COUNT(*) AS open_alerts FROM pg.public.fact_alerts WHERE UPPER(status)='OPEN'",
        "Open alerts",
    )

    text = "\n".join(lines)
    out_dir = Path("/opt/airflow/data/reports")
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"weekly_ops_brief_{end.isoformat()}.txt"
        path.write_text(text, encoding="utf-8")
        artifact = str(path)
    except Exception:
        artifact = f"memory://weekly_ops_brief_{end.isoformat()}.txt"

    return pd.DataFrame(
        [
            dict(
                report_id=random.randint(10_000_000, 99_999_999),
                report_type="WEEKLY_OPS_BRIEF",
                generated_at=now,
                period_start=start,
                period_end=end,
                status="OK",
                summary_text=text[:4000],
                artifact_path=artifact,
                model_version=MODEL,
            )
        ]
    )


def build_deliveries(con, now):
    """Dry-run delivery log for open alerts / subscriptions."""
    rows = []
    alerts = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_alerts
        WHERE UPPER(COALESCE(status,'OPEN')) = 'OPEN'
        ORDER BY created_at DESC LIMIT 20
        """,
    )
    subs = qdf(con, "SELECT * FROM pg.public.alert_subscriptions LIMIT 50")
    channels = ["LOG"]
    recipients = ["ops@oceanwatch.local"]
    if not subs.empty:
        if "channel" in subs.columns:
            channels = list(subs["channel"].dropna().astype(str).unique()) or channels
        if "email" in subs.columns:
            recipients = list(subs["email"].dropna().astype(str).unique()) or recipients
        elif "recipient" in subs.columns:
            recipients = list(subs["recipient"].dropna().astype(str).unique()) or recipients

    if alerts.empty:
        rows.append(
            dict(
                delivery_id=random.randint(10_000_000, 99_999_999),
                alert_ref="none",
                channel="LOG",
                recipient="ops@oceanwatch.local",
                status="SKIPPED",
                attempted_at=now,
                detail="No OPEN fact_alerts",
                model_version=MODEL,
            )
        )
    else:
        for _, a in alerts.iterrows():
            ref = str(a.get("title") or a.get("alert_type") or a.get("category") or "alert")
            for ch in channels[:3]:
                for rec in recipients[:5]:
                    rows.append(
                        dict(
                            delivery_id=random.randint(10_000_000, 99_999_999),
                            alert_ref=ref[:120],
                            channel=str(ch),
                            recipient=str(rec)[:120],
                            status="DRY_RUN",
                            attempted_at=now,
                            detail="Phase 16 dry-run — no external send",
                            model_version=MODEL,
                        )
                    )
    return pd.DataFrame(rows)


def build_api_usage(now):
    """Placeholder daily counters for platform monitoring."""
    endpoints = [
        "/health",
        "/v1/ocean/conditions",
        "/v1/forecasts/sst",
        "/v1/alerts",
        "/v1/port/risk",
        "/v1/gfw/effort/summary",
        "/v1/vessels/anomalies",
        "/v1/bloom/risk",
        "/v1/habitat/suitability",
    ]
    rows = [
        dict(
            usage_date=now.date(),
            endpoint=ep,
            request_count=0,
            error_count=0,
            model_version=MODEL,
        )
        for ep in endpoints
    ]
    return pd.DataFrame(rows)


def run():
    logger.info("=== Phase 16 operations & platform ===")
    now = datetime.utcnow()
    con = connect()

    health = build_health(con, now)
    write(con, "fact_system_health", health)

    report = build_report(con, now)
    write(con, "fact_report_runs", report)

    deliveries = build_deliveries(con, now)
    write(con, "fact_alert_deliveries", deliveries)

    usage = build_api_usage(now)
    write(con, "fact_api_usage_daily", usage)

    down = health[health["status"] != "UP"] if not health.empty else pd.DataFrame()
    logger.info(
        "Health checks=%s down=%s reports=%s deliveries=%s",
        len(health),
        len(down),
        len(report),
        len(deliveries),
    )
    if not report.empty:
        logger.info("Report artifact: %s", report.iloc[0].get("artifact_path"))
    logger.info("=== Phase 16 complete ===")


if __name__ == "__main__":
    run()
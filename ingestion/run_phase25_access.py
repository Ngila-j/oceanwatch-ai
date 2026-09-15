"""
Phase 25 complete — Partner Access Keys & Audit Trail.
Seeds demo API clients/keys (hashed), sample usage, and audit events
from recent pipeline products. No real secrets stored in plaintext.
"""

import hashlib
import logging
import random
from datetime import datetime, timedelta

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase25_access_v1.0"
REGION = "kenya_eez"


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


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run():
    logger.info("=== Phase 25 Partner Access & Audit ===")
    now = datetime.utcnow()
    con = connect()

    clients = pd.DataFrame(
        [
            dict(
                client_id="ow_internal",
                client_name="OceanWatch Internal UI",
                organization="OceanWatch",
                tier="INTERNAL",
                status="ACTIVE",
                contact_email="ops@oceanwatch.local",
                created_at=now,
            ),
            dict(
                client_id="partner_research",
                client_name="Demo Research Partner",
                organization="University / KMFRI demo",
                tier="RESEARCH",
                status="ACTIVE",
                contact_email="research@example.local",
                created_at=now,
            ),
            dict(
                client_id="partner_port",
                client_name="Demo Port Operator",
                organization="Port authority demo",
                tier="OPERATIONS",
                status="ACTIVE",
                contact_email="port@example.local",
                created_at=now,
            ),
            dict(
                client_id="partner_logistics",
                client_name="Demo Logistics API",
                organization="Logistics partner demo",
                tier="API",
                status="SUSPENDED",
                contact_email="api@example.local",
                created_at=now,
            ),
        ]
    )
    write(con, "dim_api_clients", clients)

    # Demo plaintext only used to create hash — never store plaintext in DB
    demo_keys = [
        ("key_internal", "ow_internal", "ow_int_", "ow_demo_internal_key_do_not_use_prod", "read:all", 100000, "ACTIVE"),
        ("key_research", "partner_research", "ow_res_", "ow_demo_research_key_do_not_use_prod", "read:ocean,read:reports", 5000, "ACTIVE"),
        ("key_port", "partner_port", "ow_prt_", "ow_demo_port_key_do_not_use_prod", "read:port,read:risk,read:alerts", 20000, "ACTIVE"),
        ("key_logistics", "partner_logistics", "ow_log_", "ow_demo_logistics_key_revoked", "read:port", 1000, "REVOKED"),
    ]
    keys_rows = []
    for key_id, client_id, prefix, raw, scopes, limit, status in demo_keys:
        keys_rows.append(
            dict(
                key_id=key_id,
                client_id=client_id,
                key_prefix=prefix,
                key_hash=hash_key(raw),
                scopes=scopes,
                rate_limit_per_day=limit,
                status=status,
                expires_at=now + timedelta(days=365) if status == "ACTIVE" else now - timedelta(days=1),
                created_at=now,
            )
        )
    write(con, "dim_api_keys", pd.DataFrame(keys_rows))

    # Sample usage based on real product endpoints
    endpoints = [
        ("/v1/ocean/conditions", "GET", 200),
        ("/v1/forecasts/sst", "GET", 200),
        ("/v1/alerts", "GET", 200),
        ("/v1/port/risk", "GET", 200),
        ("/v1/gfw/effort/summary", "GET", 200),
        ("/v1/bloom/risk", "GET", 200),
        ("/health", "GET", 200),
        ("/v1/alerts", "GET", 429),
    ]
    usage = []
    active_keys = [k for k in keys_rows if k["status"] == "ACTIVE"]
    for i in range(40):
        k = random.choice(active_keys)
        ep, method, code = random.choice(endpoints)
        usage.append(
            dict(
                usage_id=random.randint(10_000_000, 99_999_999),
                client_id=k["client_id"],
                key_id=k["key_id"],
                endpoint=ep,
                method=method,
                status_code=code,
                latency_ms=round(random.uniform(12, 220), 1),
                region_id=REGION,
                requested_at=now - timedelta(minutes=random.randint(1, 1440)),
                model_version=MODEL,
            )
        )
    write(con, "fact_api_usage", pd.DataFrame(usage))

    audit = []
    def add_audit(actor, action, entity_type, entity_id, detail):
        audit.append(
            dict(
                audit_id=random.randint(10_000_000, 99_999_999),
                actor=actor,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id),
                detail=detail,
                region_id=REGION,
                created_at=now,
                model_version=MODEL,
            )
        )

    add_audit("system", "SCHEMA_INIT", "phase", "25", "Partner access schema initialised")
    add_audit("pipeline", "PUBLISH", "event_bus", "phase22", "Event bus publish cycle")
    add_audit("pipeline", "DELIVER", "notifications", "phase23", "Notification dry-run deliveries")
    add_audit("pipeline", "GENERATE", "reports", "phase24", "Daily and weekly intelligence reports")

    runs = qdf(con, "SELECT run_id, report_type_id, overall_status FROM pg.public.fact_report_runs")
    for _, r in runs.iterrows():
        add_audit(
            "report_engine",
            "REPORT_RUN",
            "fact_report_runs",
            r.get("run_id"),
            f"{r.get('report_type_id')} status={r.get('overall_status')}",
        )

    risk = qdf(
        con,
        "SELECT composite_score, composite_level FROM pg.public.fact_unified_risk_composite ORDER BY as_of_date DESC LIMIT 1",
    )
    if not risk.empty:
        add_audit(
            "risk_engine",
            "RISK_UPDATE",
            "fact_unified_risk_composite",
            "latest",
            f"score={risk.iloc[0].get('composite_score')} level={risk.iloc[0].get('composite_level')}",
        )

    for k in keys_rows:
        add_audit(
            "access_admin",
            "KEY_UPSERT",
            "dim_api_keys",
            k["key_id"],
            f"client={k['client_id']} status={k['status']} scopes={k['scopes']}",
        )

    write(con, "fact_audit_log", pd.DataFrame(audit))

    logger.info(
        "Clients=%s keys=%s usage=%s audit=%s",
        len(clients),
        len(keys_rows),
        len(usage),
        len(audit),
    )
    logger.info("=== Phase 25 complete ===")


if __name__ == "__main__":
    run()
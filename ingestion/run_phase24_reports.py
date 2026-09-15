"""
Phase 24 complete — Automated Intelligence Report Engine.
Builds Daily Operational Brief + Weekly Ocean Brief snapshots from live facts.
Stored in Postgres for Streamlit / API / future PDF export.
"""

import logging
import random
from datetime import datetime, timedelta

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase24_reports_v1.0"
REGION = "kenya_eez"
COUNTRY = "KE"


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


def fnum(v, default=None):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        return float(v)
    except Exception:
        return default


def first_val(df, candidates, default=None):
    if df is None or df.empty:
        return default
    row = df.iloc[0]
    for c in candidates:
        if c in df.columns:
            v = row.get(c)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                return v
    return default


def section(run_id, order, code, title, status, value, label, narrative, evidence, now):
    return dict(
        section_id=random.randint(10_000_000, 99_999_999),
        run_id=run_id,
        section_order=order,
        section_code=code,
        section_title=title,
        status=status or "INFO",
        metric_value=value,
        metric_label=label,
        narrative=narrative,
        evidence=evidence,
        model_version=MODEL,
    )


def run():
    logger.info("=== Phase 24 Intelligence Reports ===")
    now = datetime.utcnow()
    con = connect()

    types = pd.DataFrame(
        [
            dict(
                report_type_id="daily_ops",
                report_name="Daily Operational Brief",
                cadence="DAILY",
                audience="Port ops / MDA desk",
                status="ACTIVE",
                notes="Composite risk, port, maritime, ocean state",
            ),
            dict(
                report_type_id="weekly_ocean",
                report_name="Weekly Ocean Brief",
                cadence="WEEKLY",
                audience="Leadership / environment / fisheries",
                status="ACTIVE",
                notes="Ocean state, ecology, fisheries conditions, WIO-OII",
            ),
        ]
    )
    write(con, "dim_report_types", types)

    risk = qdf(
        con,
        "SELECT * FROM pg.public.fact_unified_risk_composite ORDER BY as_of_date DESC LIMIT 1",
    )
    ocean = qdf(
        con,
        "SELECT * FROM pg.public.fact_ocean_state ORDER BY as_of_date DESC LIMIT 1",
    )
    stress = qdf(
        con,
        "SELECT * FROM pg.public.fact_ecological_stress ORDER BY as_of_date DESC LIMIT 1",
    )
    fish = qdf(
        con,
        "SELECT * FROM pg.public.fact_fisheries_conditions ORDER BY as_of_date DESC LIMIT 1",
    )
    port = qdf(
        con,
        "SELECT * FROM pg.public.fact_port_ops_risk ORDER BY as_of_date DESC LIMIT 1",
    )
    if port.empty:
        port = qdf(
            con,
            "SELECT * FROM pg.public.fact_port_risk ORDER BY risk_date DESC LIMIT 1",
        )
    metrics = qdf(
        con,
        "SELECT * FROM pg.public.fact_port_metrics ORDER BY metric_date DESC LIMIT 1",
    )
    wio = qdf(
        con,
        "SELECT * FROM pg.public.fact_wio_intelligence_index ORDER BY index_date DESC LIMIT 1",
    )
    events = qdf(
        con,
        """
        SELECT event_type, severity, COUNT(*) AS n
        FROM pg.public.fact_vessel_events
        GROUP BY 1, 2
        ORDER BY n DESC
        LIMIT 10
        """,
    )
    alerts = qdf(
        con,
        """
        SELECT COUNT(*) AS n
        FROM pg.public.fact_alerts
        WHERE UPPER(COALESCE(status, 'OPEN')) = 'OPEN'
        """,
    )
    notif = qdf(
        con,
        "SELECT COUNT(*) AS n FROM pg.public.fact_notification_deliveries",
    )

    composite = fnum(first_val(risk, ["composite_score"]), None)
    composite_level = str(first_val(risk, ["composite_level"], "UNKNOWN"))
    port_score = fnum(first_val(risk, ["port_score"], first_val(port, ["composite_ops_risk", "composite_risk"])), None)
    maritime_score = fnum(first_val(risk, ["maritime_score"]), None)
    ocean_score = fnum(first_val(ocean, ["ocean_state_score"]), None)
    ocean_label = str(first_val(ocean, ["ocean_state_label"], "UNKNOWN"))
    ecology = fnum(first_val(stress, ["stress_score"]), None)
    fish_score = fnum(first_val(fish, ["condition_score"]), None)
    fish_label = str(first_val(fish, ["condition_label"], "UNKNOWN"))
    wio_score = fnum(first_val(wio, ["overall_score", "overall_index"]), None)
    open_alerts = int(first_val(alerts, ["n"], 0) or 0)
    deliveries = int(first_val(notif, ["n"], 0) or 0)
    congestion = fnum(first_val(metrics, ["congestion_index"]), None)
    active_vessels = fnum(first_val(metrics, ["active_vessels"]), None)

    conf = fnum(first_val(risk, ["confidence_score"]), 75.0)

    # --- Daily ops run ---
    daily_run_id = random.randint(10_000_000, 99_999_999)
    daily_summary = (
        f"Kenya EEZ operational snapshot. Composite risk={composite} ({composite_level}). "
        f"Ocean state={ocean_score} ({ocean_label}). Open alerts={open_alerts}. "
        f"Notification deliveries logged={deliveries}."
    )
    overall = composite_level if composite is not None else ocean_label

    daily_sections = [
        section(
            daily_run_id,
            1,
            "RISK",
            "Unified risk",
            composite_level,
            composite,
            composite_level,
            f"Composite risk is {composite} ({composite_level}). Port domain remains the main driver when elevated.",
            str(first_val(risk, ["drivers"], "")),
            now,
        ),
        section(
            daily_run_id,
            2,
            "PORT",
            "Port pressure",
            "HIGH" if port_score and port_score >= 75 else "WATCH" if port_score and port_score >= 55 else "LOW",
            port_score,
            f"congestion={congestion}",
            f"Port risk score={port_score}. Active vessels={active_vessels}, congestion_index={congestion}.",
            "fact_port_ops_risk / fact_port_metrics",
            now,
        ),
        section(
            daily_run_id,
            3,
            "MARITIME",
            "Maritime behaviour",
            "WATCH" if maritime_score and maritime_score >= 55 else "LOW",
            maritime_score,
            "avg vessel risk",
            f"Maritime domain score={maritime_score}. Review Maritime Events for geofence / route patterns.",
            "fact_unified_risk + fact_vessel_events",
            now,
        ),
        section(
            daily_run_id,
            4,
            "OCEAN",
            "Ocean state",
            ocean_label,
            ocean_score,
            ocean_label,
            f"Ocean state score={ocean_score} ({ocean_label}). Ecology stress={ecology}.",
            str(first_val(ocean, ["drivers"], "fact_ocean_state")),
            now,
        ),
        section(
            daily_run_id,
            5,
            "ALERTS",
            "Open operational alerts",
            "WATCH" if open_alerts else "LOW",
            float(open_alerts),
            f"{open_alerts} open",
            f"{open_alerts} open rows in fact_alerts. Notifications dry-run deliveries={deliveries}.",
            "fact_alerts / fact_notification_deliveries",
            now,
        ),
    ]
    if not events.empty:
        top = events.iloc[0]
        daily_sections.append(
            section(
                daily_run_id,
                6,
                "EVENTS",
                "Top vessel event type",
                str(top.get("severity") or "INFO"),
                float(top.get("n") or 0),
                str(top.get("event_type")),
                f"Most frequent vessel event: {top.get('event_type')} (n={top.get('n')}, severity={top.get('severity')}).",
                "fact_vessel_events",
                now,
            )
        )

    # --- Weekly ocean run ---
    weekly_run_id = random.randint(10_000_000, 99_999_999)
    weekly_summary = (
        f"Weekly ocean intelligence for Kenya EEZ. Ocean state={ocean_score} ({ocean_label}). "
        f"Fisheries condition={fish_score} ({fish_label}). WIO-OII={wio_score}. "
        f"Ecology stress={ecology}."
    )
    weekly_sections = [
        section(
            weekly_run_id,
            1,
            "OCEAN_STATE",
            "Ocean state",
            ocean_label,
            ocean_score,
            ocean_label,
            f"Ocean state remains {ocean_label} at {ocean_score}. Use Ocean State page for drivers.",
            str(first_val(ocean, ["drivers"], "")),
            now,
        ),
        section(
            weekly_run_id,
            2,
            "ECOLOGY",
            "Ecological stress",
            str(first_val(stress, ["stress_level"], "UNKNOWN")),
            ecology,
            str(first_val(stress, ["stress_level"], "")),
            f"Ecological stress score={ecology}. Bloom/habitat fusion feeds this indicator.",
            str(first_val(stress, ["drivers"], "fact_ecological_stress")),
            now,
        ),
        section(
            weekly_run_id,
            3,
            "FISHERIES",
            "Fisheries conditions",
            fish_label,
            fish_score,
            fish_label,
            f"Fisheries environmental condition={fish_score} ({fish_label}). Not a catch forecast.",
            str(first_val(fish, ["drivers"], "fact_fisheries_conditions")),
            now,
        ),
        section(
            weekly_run_id,
            4,
            "WIO_OII",
            "WIO Intelligence Index",
            "INFO",
            wio_score,
            "overall",
            f"Western Indian Ocean Intelligence Index overall={wio_score} (methodology in drivers).",
            str(first_val(wio, ["drivers", "methodology_version"], "fact_wio_intelligence_index")),
            now,
        ),
        section(
            weekly_run_id,
            5,
            "RISK",
            "Regional composite risk",
            composite_level,
            composite,
            composite_level,
            f"Composite risk for the monitoring box={composite} ({composite_level}).",
            str(first_val(risk, ["drivers"], "")),
            now,
        ),
    ]

    runs = pd.DataFrame(
        [
            dict(
                run_id=daily_run_id,
                report_type_id="daily_ops",
                report_date=now.date(),
                region_id=REGION,
                country_id=COUNTRY,
                title=f"Daily Operational Brief — {now.date()}",
                summary=daily_summary,
                overall_status=str(overall),
                confidence_score=conf,
                section_count=len(daily_sections),
                model_version=MODEL,
                generated_at=now,
            ),
            dict(
                run_id=weekly_run_id,
                report_type_id="weekly_ocean",
                report_date=now.date(),
                region_id=REGION,
                country_id=COUNTRY,
                title=f"Weekly Ocean Brief — week of {now.date()}",
                summary=weekly_summary,
                overall_status=str(ocean_label),
                confidence_score=conf,
                section_count=len(weekly_sections),
                model_version=MODEL,
                generated_at=now,
            ),
        ]
    )
    sections_df = pd.DataFrame(daily_sections + weekly_sections)
    write(con, "fact_report_runs", runs)
    write(con, "fact_report_sections", sections_df)

    logger.info(
        "Runs=%s sections=%s | daily_status=%s weekly_ocean=%s",
        len(runs),
        len(sections_df),
        overall,
        ocean_label,
    )
    logger.info("=== Phase 24 complete ===")


if __name__ == "__main__":
    run()
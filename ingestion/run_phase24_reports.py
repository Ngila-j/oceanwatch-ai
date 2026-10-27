"""
Phase 24 — Automated Intelligence Report Engine.
Builds Daily Operational Brief + Weekly Ocean Brief from live facts.
Uses ingestion/.env OCEANWATCH_DB_URI (via db_utils).
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

import duckdb
import pandas as pd

from db_utils import get_db_uri

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase24_reports_v1.0"
REGION = "kenya_eez"
COUNTRY = "KE"


def connect():
    uri = get_db_uri()
    logger.info("Phase 24 reports → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{uri}' AS pg (TYPE POSTGRES)")
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


def section(run_id, order, code, title, status, value, label, narrative, evidence):
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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
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

    # Live signals (soft-fail)
    ais = qdf(
        con,
        """
        SELECT COUNT(*) AS n,
               AVG(sog) AS avg_sog,
               COUNT(DISTINCT mmsi) AS vessels
        FROM pg.public.fact_ais_positions
        WHERE event_time > now() - INTERVAL '7 days'
        """,
    )
    ocean = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_ocean_conditions
        ORDER BY date_key DESC LIMIT 5
        """,
    )
    port = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_port_metrics
        ORDER BY metric_date DESC LIMIT 5
        """,
    )
    wio = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_wio_intelligence_index
        WHERE region_id = 'kenya_eez'
        ORDER BY index_date DESC LIMIT 5
        """,
    )
    alerts = qdf(
        con,
        """
        SELECT COUNT(*) AS n FROM pg.public.fact_alerts
        WHERE created_at > now() - INTERVAL '7 days'
        """,
    )
    gfw = qdf(
        con,
        """
        SELECT AVG(hours) AS avg_hours, SUM(hours) AS sum_hours, COUNT(*) AS cells
        FROM pg.public.fact_gfw_fishing_effort
        """,
    )

    vessels = int(fnum(first_val(ais, ["vessels"]), 0) or 0)
    ais_n = int(fnum(first_val(ais, ["n"]), 0) or 0)
    avg_sog = fnum(first_val(ais, ["avg_sog"]), None)
    sst = fnum(first_val(ocean, ["sst_celsius", "sst", "sea_surface_temp"]), None)
    chl = fnum(first_val(ocean, ["chlorophyll", "chl_mg_m3", "chlorophyll_a"]), None)
    cong = fnum(first_val(port, ["congestion_index", "congestion"]), None)
    arrivals = fnum(first_val(port, ["arrivals", "vessel_arrivals"]), None)
    overall_wio = fnum(first_val(wio, ["overall_score"]), None)
    ocean_h = fnum(first_val(wio, ["ocean_health_score"]), None)
    fish_p = fnum(first_val(wio, ["fishing_pressure_score"]), None)
    alert_n = int(fnum(first_val(alerts, ["n"]), 0) or 0)
    gfw_hours = fnum(first_val(gfw, ["sum_hours"]), None)

    # Status helpers
    def band(score, high_bad=False):
        if score is None:
            return "INFO"
        s = float(score)
        if high_bad:
            if s >= 70:
                return "HIGH"
            if s >= 40:
                return "WATCH"
            return "OK"
        if s >= 70:
            return "OK"
        if s >= 40:
            return "WATCH"
        return "HIGH"

    port_status = band(cong, high_bad=True) if cong is not None else "INFO"
    ocean_status = "OK"
    if sst is not None and (sst < 24 or sst > 30):
        ocean_status = "WATCH"
    if sst is not None and (sst < 22 or sst > 31):
        ocean_status = "HIGH"

    overall = "OK"
    for s in (port_status, ocean_status):
        if s == "HIGH":
            overall = "HIGH"
            break
        if s == "WATCH" and overall == "OK":
            overall = "WATCH"

    conf = 65.0
    if vessels:
        conf += 8
    if sst is not None:
        conf += 8
    if overall_wio is not None:
        conf += 6
    conf = min(95.0, conf)

    daily_run_id = int(now.strftime("%Y%m%d")) * 10 + 1
    weekly_run_id = int(now.strftime("%Y%m%d")) * 10 + 2

    daily_sections = [
        section(
            daily_run_id,
            1,
            "maritime_ais",
            "Maritime / AIS picture",
            "OK" if vessels else "INFO",
            float(vessels),
            "distinct vessels (7d)",
            f"Kenya EEZ AIS sample shows {vessels} distinct vessels "
            f"({ais_n} positions). "
            + (f"Mean SOG {avg_sog:.1f} kn. " if avg_sog is not None else "")
            + "Decision-support only — coverage is partial.",
            "fact_ais_positions",
        ),
        section(
            daily_run_id,
            2,
            "port_congestion",
            "Port congestion (Mombasa signal)",
            port_status,
            cong,
            "congestion index" if cong is not None else "n/a",
            (
                f"Latest port congestion index ≈ {cong:.1f}. "
                + (f"Arrivals signal: {arrivals}. " if arrivals is not None else "")
                + "Monitor berth pressure and anchorage dwell."
                if cong is not None
                else "No fact_port_metrics row available — seed port metrics for live scores."
            ),
            "fact_port_metrics",
        ),
        section(
            daily_run_id,
            3,
            "ocean_state",
            "Nearshore ocean state",
            ocean_status,
            sst,
            "SST °C" if sst is not None else "n/a",
            (
                f"Latest SST ≈ {sst:.2f} °C"
                + (f"; chlorophyll proxy {chl:.3f}." if chl is not None else ".")
                if sst is not None
                else "No ocean conditions row — run ocean seed / Copernicus ingest."
            ),
            "fact_ocean_conditions",
        ),
        section(
            daily_run_id,
            4,
            "alerts",
            "Open / recent alerts",
            "WATCH" if alert_n else "OK",
            float(alert_n),
            "alerts (7d)",
            f"{alert_n} alert row(s) in the last 7 days. Review Alert Center for triage.",
            "fact_alerts",
        ),
        section(
            daily_run_id,
            5,
            "wio_index",
            "WIO Intelligence Index (latest)",
            band(overall_wio) if overall_wio is not None else "INFO",
            overall_wio,
            "overall score" if overall_wio is not None else "n/a",
            (
                f"Latest Kenya EEZ overall WIO-OII ≈ {overall_wio:.1f} "
                f"(ocean health {ocean_h}, fishing pressure {fish_p})."
                if overall_wio is not None
                else "WIO index not computed yet."
            ),
            "fact_wio_intelligence_index",
        ),
    ]

    ocean_label = ocean_status if sst is not None else (
        band(ocean_h) if ocean_h is not None else "INFO"
    )

    weekly_sections = [
        section(
            weekly_run_id,
            1,
            "sst_week",
            "Sea surface temperature",
            ocean_status,
            sst,
            "SST °C" if sst is not None else "n/a",
            (
                f"Weekly ocean brief: SST holding near {sst:.2f} °C for Kenya EEZ watch boxes."
                if sst is not None
                else "SST series unavailable this week."
            ),
            "fact_ocean_conditions",
        ),
        section(
            weekly_run_id,
            2,
            "fishing_effort",
            "Fishing pressure / GFW effort",
            band(fish_p) if fish_p is not None else "INFO",
            gfw_hours if gfw_hours is not None else fish_p,
            "GFW hours sum" if gfw_hours is not None else "fishing pressure score",
            (
                f"Aggregated GFW effort hours ≈ {gfw_hours:.1f} across demo/live cells. "
                if gfw_hours is not None
                else ""
            )
            + (
                f"WIO fishing-pressure component ≈ {fish_p:.1f}."
                if fish_p is not None
                else "No fishing-pressure score yet."
            ),
            "fact_gfw_fishing_effort / WIO index",
        ),
        section(
            weekly_run_id,
            3,
            "ocean_health",
            "Ocean health component",
            band(ocean_h) if ocean_h is not None else "INFO",
            ocean_h,
            "ocean health score",
            (
                f"WIO ocean-health score ≈ {ocean_h:.1f}."
                if ocean_h is not None
                else "Ocean-health component missing."
            ),
            "fact_wio_intelligence_index",
        ),
        section(
            weekly_run_id,
            4,
            "composite",
            "Composite weekly outlook",
            overall,
            overall_wio,
            "WIO overall",
            f"Composite outlook status **{overall}** for Kenya EEZ. "
            "Use with AIS, port, and ecology layers — not a navigational product.",
            "phase24 composite",
        ),
    ]

    daily_summary = (
        f"Daily Operational Brief for {now.date()} (Kenya EEZ). "
        f"Status {overall}. Vessels≈{vessels}, alerts(7d)={alert_n}"
        + (f", SST≈{sst:.1f}°C" if sst is not None else "")
        + (f", congestion≈{cong:.0f}" if cong is not None else "")
        + "."
    )
    weekly_summary = (
        f"Weekly Ocean Brief — week of {now.date()}. "
        f"Ocean label {ocean_label}. "
        + (f"WIO overall≈{overall_wio:.1f}. " if overall_wio is not None else "")
        + "Rollup of SST, fishing pressure, and index components."
    )

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
    con.close()


if __name__ == "__main__":
    run()

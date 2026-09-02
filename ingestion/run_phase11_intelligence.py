"""
Phase 11 complete runner (Kenya EEZ).
Freshness → spatial → events → risks → alerts (from events) → provenance.
"""

import logging
import random
from datetime import datetime

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase11_v1.0"
REGION = "kenya_eez"
PIPELINE = "oceanwatch_pipeline_v1.8"

# Kenya / WIO monitoring box
MIN_LAT, MAX_LAT = -6.0, 3.0
MIN_LON, MAX_LON = 38.0, 46.0
MOMBASA = (-4.05, 39.67)


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


def write(con, table, df):
    if df is None or df.empty:
        return
    use = [c for c in df.columns if c in cols(con, table)]
    if not use:
        logger.warning("No matching columns for %s", table)
        return
    con.register("_t", df[use])
    con.execute(f"DELETE FROM pg.public.{table}")
    con.execute(
        f"INSERT INTO pg.public.{table} ({', '.join(use)}) SELECT {', '.join(use)} FROM _t"
    )
    logger.info("%s: %s rows", table, len(df))


def age_min(ts):
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return 99999.0
    try:
        t = pd.to_datetime(ts)
        if getattr(t, "tzinfo", None) is not None:
            t = t.tz_localize(None)
        return max(0.0, (datetime.utcnow() - t.to_pydatetime()).total_seconds() / 60.0)
    except Exception:
        return 99999.0


def status_from_age(mins, daily=False):
    if mins >= 99999:
        return "UNKNOWN"
    if daily:
        if mins <= 36 * 60:
            return "DAILY_OK"
        return "STALE"
    if mins <= 180:
        return "LIVE"
    if mins <= 24 * 60:
        return "DELAYED"
    return "STALE"


def conf(base, mins):
    if mins > 48 * 60:
        return max(15.0, base - 45)
    if mins > 24 * 60:
        return max(25.0, base - 30)
    if mins > 6 * 60:
        return max(40.0, base - 15)
    return base


def qdf(con, sql):
    try:
        return con.execute(sql).fetchdf()
    except Exception as e:
        logger.warning("Query failed: %s", e)
        return pd.DataFrame()


def build_freshness(con, now):
    rows = []

    ocean = qdf(
        con,
        """
        SELECT MAX(date_key) AS ts, COUNT(*) AS n
        FROM pg.public.fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL
        """,
    )
    ts = ocean.iloc[0]["ts"] if not ocean.empty else None
    n = int(ocean.iloc[0]["n"] or 0) if not ocean.empty else 0
    am = age_min(ts)
    rows.append(
        dict(
            source_key="copernicus_sst",
            source_name="Copernicus SST (daily mean)",
            last_timestamp=ts,
            age_minutes=round(am, 1),
            status=status_from_age(am, daily=True),
            record_count=n,
            notes="fact_ocean_conditions.sst_celsius",
            checked_at=now,
        )
    )

    chl = qdf(
        con,
        """
        SELECT MAX(date_key) AS ts, COUNT(*) AS n
        FROM pg.public.fact_ocean_conditions
        WHERE chlorophyll_mg_m3 IS NOT NULL
        """,
    )
    ts = chl.iloc[0]["ts"] if not chl.empty else None
    n = int(chl.iloc[0]["n"] or 0) if not chl.empty else 0
    am = age_min(ts)
    rows.append(
        dict(
            source_key="copernicus_chl",
            source_name="Copernicus Chlorophyll",
            last_timestamp=ts,
            age_minutes=round(am, 1),
            status=status_from_age(am, daily=True),
            record_count=n,
            notes="fact_ocean_conditions.chlorophyll_mg_m3",
            checked_at=now,
        )
    )

    tides = qdf(con, "SELECT MAX(t::TIMESTAMP) AS ts, COUNT(*) AS n FROM pg.public.raw_tides")
    if tides.empty:
        tides = qdf(
            con,
            "SELECT MAX(observation_time) AS ts, COUNT(*) AS n FROM pg.public.stg_tides",
        )
    ts = tides.iloc[0]["ts"] if not tides.empty else None
    n = int(tides.iloc[0]["n"] or 0) if not tides.empty else 0
    am = age_min(ts)
    rows.append(
        dict(
            source_key="noaa_tides",
            source_name="NOAA tides / water level",
            last_timestamp=ts,
            age_minutes=round(am, 1),
            status=status_from_age(am, daily=True),
            record_count=n,
            notes="raw_tides/stg_tides",
            checked_at=now,
        )
    )

    ais = qdf(
        con,
        """
        SELECT MAX(event_time) AS ts, COUNT(*) AS n
        FROM pg.public.fact_ais_positions
        """,
    )
    ts = ais.iloc[0]["ts"] if not ais.empty else None
    n = int(ais.iloc[0]["n"] or 0) if not ais.empty else 0
    am = age_min(ts)
    rows.append(
        dict(
            source_key="ais",
            source_name="AIS positions",
            last_timestamp=ts,
            age_minutes=round(am, 1),
            status=status_from_age(am),
            record_count=n,
            notes="SAMPLE and/or AISSTREAM",
            checked_at=now,
        )
    )

    gfw = qdf(
        con,
        """
        SELECT MAX(effort_date) AS ts, COUNT(*) AS n
        FROM pg.public.fact_gfw_fishing_effort
        """,
    )
    ts = gfw.iloc[0]["ts"] if not gfw.empty else None
    n = int(gfw.iloc[0]["n"] or 0) if not gfw.empty else 0
    am = age_min(ts)
    rows.append(
        dict(
            source_key="gfw",
            source_name="Global Fishing Watch effort",
            last_timestamp=ts,
            age_minutes=round(am, 1),
            status=status_from_age(am, daily=True),
            record_count=n,
            notes="Attribution required",
            checked_at=now,
        )
    )

    port = qdf(
        con,
        "SELECT MAX(metric_date) AS ts, COUNT(*) AS n FROM pg.public.fact_port_metrics",
    )
    ts = port.iloc[0]["ts"] if not port.empty else None
    n = int(port.iloc[0]["n"] or 0) if not port.empty else 0
    am = age_min(ts)
    rows.append(
        dict(
            source_key="port_mombasa",
            source_name="Mombasa port metrics",
            last_timestamp=ts,
            age_minutes=round(am, 1),
            status=status_from_age(am, daily=True),
            record_count=n,
            notes="Seeded/derived metrics",
            checked_at=now,
        )
    )

    return pd.DataFrame(rows)


def build_spatial(con, now):
    rows = []
    ais = qdf(
        con,
        f"""
        SELECT mmsi, latitude, longitude, event_time, source
        FROM pg.public.fact_ais_positions
        WHERE latitude BETWEEN {MIN_LAT} AND {MAX_LAT}
          AND longitude BETWEEN {MIN_LON} AND {MAX_LON}
        """,
    )
    n_pos = len(ais)
    n_ves = int(ais["mmsi"].nunique()) if n_pos else 0
    rows.append(
        dict(
            metric_key="ais_in_kenya_box",
            metric_label="AIS positions in Kenya/WIO box",
            metric_value=float(n_pos),
            unit="positions",
            region_id=REGION,
            details=f"vessels={n_ves}",
            model_version=MODEL,
            computed_at=now,
        )
    )
    rows.append(
        dict(
            metric_key="ais_vessels_in_kenya_box",
            metric_label="Distinct vessels in Kenya/WIO box",
            metric_value=float(n_ves),
            unit="vessels",
            region_id=REGION,
            details=f"bbox=[{MIN_LAT},{MAX_LAT}]x[{MIN_LON},{MAX_LON}]",
            model_version=MODEL,
            computed_at=now,
        )
    )

    near = 0
    if n_pos:
        lat0, lon0 = MOMBASA
        # Parentheses required so each comparison is boolean before &
        near = int(
            (
                ((ais["latitude"] - lat0).abs() < 0.35)
                & ((ais["longitude"] - lon0).abs() < 0.35)
            ).sum()
        )
    rows.append(
        dict(
            metric_key="ais_near_mombasa",
            metric_label="AIS positions near Mombasa (~0.35 deg)",
            metric_value=float(near),
            unit="positions",
            region_id=REGION,
            details="approx port approaches",
            model_version=MODEL,
            computed_at=now,
        )
    )

    gfw = qdf(
        con,
        f"""
        SELECT COALESCE(SUM(hours),0) AS hours
        FROM pg.public.fact_gfw_fishing_effort
        WHERE lat BETWEEN {MIN_LAT} AND {MAX_LAT}
          AND lon BETWEEN {MIN_LON} AND {MAX_LON}
        """,
    )
    if gfw.empty:
        gfw = qdf(
            con,
            "SELECT COALESCE(SUM(hours),0) AS hours FROM pg.public.fact_gfw_fishing_effort",
        )
    hours = float(gfw.iloc[0]["hours"] or 0) if not gfw.empty else 0.0
    rows.append(
        dict(
            metric_key="gfw_hours_kenya_box",
            metric_label="GFW fishing hours (stored)",
            metric_value=hours,
            unit="hours",
            region_id=REGION,
            details="Powered by Global Fishing Watch",
            model_version=MODEL,
            computed_at=now,
        )
    )
    return pd.DataFrame(rows)


def build_events_risks(con, now, freshness_df):
    events, risks = [], []
    fmap = {r["source_key"]: r for _, r in freshness_df.iterrows()}

    def am(key):
        return float(fmap.get(key, {}).get("age_minutes") or 99999)

    port = qdf(
        con,
        "SELECT * FROM pg.public.fact_port_metrics ORDER BY metric_date DESC LIMIT 1",
    )
    if not port.empty:
        p = port.iloc[0]
        level = str(p.get("congestion_level") or "").upper()
        idx = float(p.get("congestion_index") or 0)
        score = min(
            100.0,
            idx if idx else (85 if level == "HIGH" else 55 if level == "MODERATE" else 25),
        )
        c = conf(88, am("port_mombasa"))
        sev = "HIGH" if score >= 75 else "ELEVATED" if score >= 50 else "INFO"
        events.append(
            dict(
                event_id=random.randint(10_000_000, 99_999_999),
                event_type="PORT_CONGESTION",
                event_category="PORT",
                severity=sev,
                event_time=now,
                latitude=MOMBASA[0],
                longitude=MOMBASA[1],
                region_id=REGION,
                entity_id="mombasa",
                confidence_score=round(c, 1),
                risk_score=round(score, 1),
                model_version=MODEL,
                source="fact_port_metrics",
                title=f"Mombasa port congestion {level or 'UNKNOWN'}",
                description=f"index={idx} active={p.get('active_vessels')}",
                evidence=f"metric_date={p.get('metric_date')}",
                status="OPEN",
                created_at=now,
            )
        )
        risks.append(
            dict(
                risk_id=random.randint(10_000_000, 99_999_999),
                domain="PORT",
                entity_id="mombasa",
                region_id=REGION,
                risk_score=round(score, 1),
                confidence_score=round(c, 1),
                risk_level=sev,
                reason=f"Congestion {level}, index {idx}",
                data_freshness_minutes=round(am("port_mombasa"), 1),
                model_version=MODEL,
                as_of_time=now,
                created_at=now,
            )
        )

    ves = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_vessel_anomalies
        WHERE risk_score >= 55
        ORDER BY risk_score DESC LIMIT 20
        """,
    )
    for _, v in ves.iterrows():
        score = float(v.get("risk_score") or 0)
        c = conf(float(v.get("confidence_score") or 65), am("ais"))
        sev = "HIGH" if score >= 80 else "ELEVATED"
        events.append(
            dict(
                event_id=random.randint(10_000_000, 99_999_999),
                event_type="VESSEL_BEHAVIOUR",
                event_category="MARITIME",
                severity=sev,
                event_time=now,
                latitude=None,
                longitude=None,
                region_id=REGION,
                entity_id=str(v.get("vessel_name") or "unknown"),
                confidence_score=round(c, 1),
                risk_score=round(score, 1),
                model_version=MODEL,
                source="fact_vessel_anomalies",
                title=f"Vessel behaviour flag — {v.get('vessel_name')}",
                description="Heuristic score for human review only",
                evidence=str(v.get("evidence") or ""),
                status="OPEN",
                created_at=now,
            )
        )
        risks.append(
            dict(
                risk_id=random.randint(10_000_000, 99_999_999),
                domain="VESSEL",
                entity_id=str(v.get("vessel_name") or ""),
                region_id=REGION,
                risk_score=round(score, 1),
                confidence_score=round(c, 1),
                risk_level=sev,
                reason=str(v.get("evidence") or "behaviour features"),
                data_freshness_minutes=round(am("ais"), 1),
                model_version=MODEL,
                as_of_time=now,
                created_at=now,
            )
        )

    bloom = qdf(
        con,
        "SELECT * FROM pg.public.fact_bloom_risk ORDER BY risk_date DESC LIMIT 1",
    )
    if not bloom.empty:
        b = bloom.iloc[0]
        prob = float(b.get("bloom_probability") or b.get("probability") or 0)
        if prob >= 30:
            score = min(100.0, prob)
            c = conf(82, am("copernicus_chl"))
            sev = "HIGH" if score >= 70 else "ELEVATED" if score >= 50 else "INFO"
            events.append(
                dict(
                    event_id=random.randint(10_000_000, 99_999_999),
                    event_type="BLOOM_RISK",
                    event_category="ENVIRONMENT",
                    severity=sev,
                    event_time=now,
                    latitude=None,
                    longitude=None,
                    region_id=REGION,
                    entity_id=REGION,
                    confidence_score=round(c, 1),
                    risk_score=round(score, 1),
                    model_version=MODEL,
                    source="fact_bloom_risk",
                    title=f"Bloom risk {score:.0f}",
                    description=str(b.get("drivers") or b.get("risk_level") or ""),
                    evidence=f"prob={prob}",
                    status="OPEN",
                    created_at=now,
                )
            )
            risks.append(
                dict(
                    risk_id=random.randint(10_000_000, 99_999_999),
                    domain="OCEAN",
                    entity_id=REGION,
                    region_id=REGION,
                    risk_score=round(score, 1),
                    confidence_score=round(c, 1),
                    risk_level=sev,
                    reason=f"Bloom probability {prob}",
                    data_freshness_minutes=round(am("copernicus_chl"), 1),
                    model_version=MODEL,
                    as_of_time=now,
                    created_at=now,
                )
            )

    sst = qdf(
        con,
        """
        SELECT date_key, sst_celsius FROM pg.public.fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL ORDER BY date_key DESC LIMIT 30
        """,
    )
    if len(sst) >= 5:
        latest = float(sst.iloc[0]["sst_celsius"])
        mean = float(sst["sst_celsius"].mean())
        delta = latest - mean
        if abs(delta) >= 0.25:
            score = min(100.0, 35 + abs(delta) * 50)
            c = conf(80, am("copernicus_sst"))
            sev = "ELEVATED" if abs(delta) >= 0.5 else "INFO"
            events.append(
                dict(
                    event_id=random.randint(10_000_000, 99_999_999),
                    event_type="SST_ANOMALY",
                    event_category="OCEAN",
                    severity=sev,
                    event_time=now,
                    latitude=None,
                    longitude=None,
                    region_id=REGION,
                    entity_id=REGION,
                    confidence_score=round(c, 1),
                    risk_score=round(score, 1),
                    model_version=MODEL,
                    source="fact_ocean_conditions",
                    title=f"SST vs recent mean {delta:+.2f} C",
                    description=f"latest={latest:.2f} mean={mean:.2f}",
                    evidence=f"n={len(sst)}",
                    status="OPEN",
                    created_at=now,
                )
            )
            risks.append(
                dict(
                    risk_id=random.randint(10_000_000, 99_999_999),
                    domain="OCEAN",
                    entity_id=REGION,
                    region_id=REGION,
                    risk_score=round(score, 1),
                    confidence_score=round(c, 1),
                    risk_level=sev,
                    reason=f"SST delta {delta:+.2f} C",
                    data_freshness_minutes=round(am("copernicus_sst"), 1),
                    model_version=MODEL,
                    as_of_time=now,
                    created_at=now,
                )
            )

    return pd.DataFrame(events), pd.DataFrame(risks)


def build_provenance(con, now):
    rows = []
    ocean = qdf(
        con,
        """
        SELECT date_key, sst_celsius, chlorophyll_mg_m3
        FROM pg.public.fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL
        ORDER BY date_key DESC LIMIT 1
        """,
    )
    if not ocean.empty:
        o = ocean.iloc[0]
        rows.append(
            dict(
                metric_key="sst_latest",
                metric_label="Latest SST",
                value_text=f"{float(o['sst_celsius']):.3f} C",
                source_system="Copernicus Marine",
                dataset_name="GLOBAL analysis/forecast PHY thetao summary",
                observed_at=o["date_key"],
                pipeline_version=PIPELINE,
                quality_flag="GOOD",
                region_id=REGION,
                created_at=now,
            )
        )
        if pd.notna(o.get("chlorophyll_mg_m3")):
            rows.append(
                dict(
                    metric_key="chl_latest",
                    metric_label="Latest Chlorophyll",
                    value_text=f"{float(o['chlorophyll_mg_m3']):.4f} mg/m3",
                    source_system="Copernicus Marine",
                    dataset_name="CHL daily summary",
                    observed_at=o["date_key"],
                    pipeline_version=PIPELINE,
                    quality_flag="GOOD",
                    region_id=REGION,
                    created_at=now,
                )
            )

    wio = qdf(
        con,
        "SELECT * FROM pg.public.fact_wio_intelligence_index ORDER BY index_date DESC LIMIT 1",
    )
    if not wio.empty:
        w = wio.iloc[0]
        rows.append(
            dict(
                metric_key="wio_oii",
                metric_label="WIO-OII overall",
                value_text=str(w.get("overall_score")),
                source_system="OceanWatch",
                dataset_name="fact_wio_intelligence_index",
                observed_at=w.get("index_date"),
                pipeline_version=PIPELINE,
                quality_flag="MODEL",
                region_id=REGION,
                created_at=now,
            )
        )

    gfw = qdf(
        con,
        """
        SELECT COALESCE(SUM(hours),0) AS hours, MAX(effort_date) AS ts
        FROM pg.public.fact_gfw_fishing_effort
        """,
    )
    if not gfw.empty:
        rows.append(
            dict(
                metric_key="gfw_hours",
                metric_label="GFW effort hours stored",
                value_text=f"{float(gfw.iloc[0]['hours'] or 0):.1f}",
                source_system="Global Fishing Watch",
                dataset_name="4Wings effort API extract",
                observed_at=gfw.iloc[0]["ts"],
                pipeline_version=PIPELINE,
                quality_flag="GOOD",
                region_id=REGION,
                created_at=now,
            )
        )
    return pd.DataFrame(rows)


def sync_alerts_from_events(con, events: pd.DataFrame, now):
    if events is None or events.empty:
        return
    try:
        con.execute(
            """
            DELETE FROM pg.public.fact_alerts
            WHERE status = 'OPEN'
              AND title LIKE 'P11:%'
            """
        )
    except Exception as e:
        logger.warning("alert cleanup: %s", e)

    rows = []
    for _, e in events.iterrows():
        rows.append(
            {
                "alert_date": now.date(),
                "alert_type": e.get("event_category"),
                "category": e.get("event_category"),
                "severity": e.get("severity"),
                "title": f"P11: {e.get('title')}",
                "message": e.get("description"),
                "value": e.get("risk_score"),
                "risk_score": e.get("risk_score"),
                "status": "OPEN",
                "created_at": now,
            }
        )
    df = pd.DataFrame(rows)
    use = [c for c in df.columns if c in cols(con, "fact_alerts")]
    if not use:
        logger.warning("Could not sync alerts — column mismatch")
        return
    con.register("_al", df[use])
    con.execute(
        f"INSERT INTO pg.public.fact_alerts ({', '.join(use)}) SELECT {', '.join(use)} FROM _al"
    )
    logger.info("Synced %s alerts from events", len(df))


def run():
    logger.info("=== Phase 11 complete intelligence ===")
    now = datetime.utcnow()
    con = connect()

    freshness = build_freshness(con, now)
    write(con, "data_freshness", freshness)

    spatial = build_spatial(con, now)
    write(con, "spatial_intelligence", spatial)

    events, risks = build_events_risks(con, now, freshness)
    write(con, "oceanwatch_events", events)
    write(con, "risk_scores", risks)

    prov = build_provenance(con, now)
    write(con, "data_provenance", prov)

    sync_alerts_from_events(con, events, now)

    logger.info(
        "Freshness=%s spatial=%s events=%s risks=%s provenance=%s",
        len(freshness),
        len(spatial),
        len(events),
        len(risks),
        len(prov),
    )
    logger.info("=== Phase 11 complete ===")


if __name__ == "__main__":
    run()
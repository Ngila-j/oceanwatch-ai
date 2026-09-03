"""
Phase 13 complete — Ocean Intelligence (Kenya EEZ).
Climate anomalies + multi-variable risk fusion + environmental early warnings.
"""

import logging
import random
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase13_ocean_v1.0"
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
                WHERE table_schema='public' AND table_name=?
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
        logger.warning("No matching columns for %s", table)
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


def severity_from_pct(pct):
    ap = abs(pct)
    if ap >= 15:
        return "HIGH"
    if ap >= 8:
        return "ELEVATED"
    if ap >= 4:
        return "WATCH"
    return "NORMAL"


def conf_from_n(n, base=85.0):
    if n < 5:
        return max(40.0, base - 30)
    if n < 14:
        return max(55.0, base - 15)
    return base


def build_climate_anomalies(ocean: pd.DataFrame, now):
    rows = []
    if ocean.empty:
        return pd.DataFrame()

    ocean = ocean.copy()
    ocean["date_key"] = pd.to_datetime(ocean["date_key"])
    ocean = ocean.sort_values("date_key")

    for metric, col in [("SST", "sst_celsius"), ("CHL", "chlorophyll_mg_m3")]:
        s = ocean.dropna(subset=[col]).copy()
        if s.empty:
            continue
        latest = s.iloc[-1]
        cur = float(latest[col])
        last7 = s.tail(7)[col]
        last30 = s.tail(30)[col]
        m7 = float(last7.mean()) if len(last7) else cur
        m30 = float(last30.mean()) if len(last30) else cur
        anom = cur - m30
        pct = (anom / m30 * 100.0) if m30 else 0.0
        sev = severity_from_pct(pct)
        rows.append(
            dict(
                as_of_date=latest["date_key"].date()
                if hasattr(latest["date_key"], "date")
                else latest["date_key"],
                region_id=REGION,
                metric=metric,
                current_value=round(cur, 4),
                mean_7d=round(m7, 4),
                mean_30d=round(m30, 4),
                anomaly_value=round(anom, 4),
                anomaly_pct=round(pct, 2),
                severity=sev,
                confidence_score=round(conf_from_n(len(s)), 1),
                model_version=MODEL,
                created_at=now,
            )
        )
    return pd.DataFrame(rows)


def build_fusion(con, anomalies: pd.DataFrame, now):
    ocean = qdf(
        con,
        """
        SELECT date_key, sst_celsius, chlorophyll_mg_m3
        FROM pg.public.fact_ocean_conditions
        ORDER BY date_key DESC LIMIT 1
        """,
    )
    bloom = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_bloom_risk
        ORDER BY risk_date DESC LIMIT 1
        """,
    )
    habitat = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_habitat_suitability
        ORDER BY as_of_date DESC LIMIT 1
        """,
    )

    sst = chl = bloom_p = habitat_s = None
    drivers = []

    if not ocean.empty:
        o = ocean.iloc[0]
        if pd.notna(o.get("sst_celsius")):
            sst = float(o["sst_celsius"])
        if pd.notna(o.get("chlorophyll_mg_m3")):
            chl = float(o["chlorophyll_mg_m3"])

    if not bloom.empty:
        b = bloom.iloc[0]
        bloom_p = float(b.get("bloom_probability") or b.get("probability") or 0)
        drivers.append(f"bloom_prob={bloom_p:.1f}")

    if not habitat.empty:
        h = habitat.iloc[0]
        habitat_s = float(
            h.get("suitability_score") or h.get("score") or h.get("habitat_score") or 0
        )
        drivers.append(f"habitat={habitat_s:.1f}")

    # Climate risk from anomaly severity
    climate_risk = 20.0
    if not anomalies.empty:
        for _, a in anomalies.iterrows():
            sev = str(a.get("severity") or "")
            ap = abs(float(a.get("anomaly_pct") or 0))
            if sev == "HIGH":
                climate_risk = max(climate_risk, min(100.0, 55 + ap))
            elif sev == "ELEVATED":
                climate_risk = max(climate_risk, min(100.0, 40 + ap))
            elif sev == "WATCH":
                climate_risk = max(climate_risk, min(100.0, 25 + ap * 0.5))
            drivers.append(f"{a['metric']}_anom={a.get('anomaly_pct')}%")

    bloom_risk = float(bloom_p) if bloom_p is not None else 15.0
    # Habitat stress = inverse of suitability (high suitability = low stress)
    if habitat_s is not None:
        habitat_stress = max(0.0, min(100.0, 100.0 - habitat_s))
    else:
        habitat_stress = 30.0

    # Optional SST thermal stress proxy
    if sst is not None and sst >= 29.5:
        climate_risk = max(climate_risk, 70.0)
        drivers.append(f"sst_thermal={sst:.2f}")

    composite = (
        0.35 * climate_risk
        + 0.35 * bloom_risk
        + 0.30 * habitat_stress
    )
    composite = float(min(100.0, max(0.0, composite)))

    if composite >= 75:
        level = "HIGH"
    elif composite >= 55:
        level = "ELEVATED"
    elif composite >= 35:
        level = "WATCH"
    else:
        level = "LOW"

    conf = 75.0
    if anomalies is not None and not anomalies.empty:
        conf = float(np.mean(anomalies["confidence_score"]))

    early = composite >= 55 or bloom_risk >= 50 or climate_risk >= 60
    msg = None
    if early:
        parts = []
        if bloom_risk >= 50:
            parts.append("elevated bloom signal")
        if climate_risk >= 60:
            parts.append("climate/SST anomaly pressure")
        if habitat_stress >= 50:
            parts.append("habitat stress")
        msg = "Early warning: " + ", ".join(parts) if parts else "Elevated ocean composite risk"

    as_of = now.date()
    if not ocean.empty:
        try:
            as_of = pd.to_datetime(ocean.iloc[0]["date_key"]).date()
        except Exception:
            pass

    return pd.DataFrame(
        [
            dict(
                as_of_date=as_of,
                region_id=REGION,
                sst_celsius=sst,
                chlorophyll_mg_m3=chl,
                bloom_probability=bloom_p,
                habitat_score=habitat_s,
                climate_risk_score=round(climate_risk, 1),
                bloom_risk_score=round(bloom_risk, 1),
                habitat_stress_score=round(habitat_stress, 1),
                composite_ocean_risk=round(composite, 1),
                risk_level=level,
                confidence_score=round(conf, 1),
                early_warning_flag=bool(early),
                early_warning_message=msg,
                drivers=" | ".join(drivers) if drivers else "baseline",
                model_version=MODEL,
                created_at=now,
            )
        ]
    )


def build_warnings(fusion: pd.DataFrame, anomalies: pd.DataFrame, now):
    rows = []
    if fusion is not None and not fusion.empty:
        f = fusion.iloc[0]
        if f.get("early_warning_flag"):
            rows.append(
                dict(
                    warning_id=random.randint(10_000_000, 99_999_999),
                    as_of_date=f["as_of_date"],
                    region_id=REGION,
                    warning_type="OCEAN_COMPOSITE",
                    severity=f.get("risk_level"),
                    title=f"Ocean composite risk {f.get('risk_level')}",
                    message=f.get("early_warning_message") or f.get("drivers"),
                    metric_value=float(f.get("composite_ocean_risk") or 0),
                    confidence_score=float(f.get("confidence_score") or 70),
                    status="OPEN",
                    model_version=MODEL,
                    created_at=now,
                )
            )
        if float(f.get("bloom_risk_score") or 0) >= 50:
            rows.append(
                dict(
                    warning_id=random.randint(10_000_000, 99_999_999),
                    as_of_date=f["as_of_date"],
                    region_id=REGION,
                    warning_type="BLOOM",
                    severity="ELEVATED" if float(f["bloom_risk_score"]) < 70 else "HIGH",
                    title="Bloom risk elevated",
                    message=f"Bloom probability/score {f.get('bloom_risk_score')}",
                    metric_value=float(f["bloom_risk_score"]),
                    confidence_score=float(f.get("confidence_score") or 70),
                    status="OPEN",
                    model_version=MODEL,
                    created_at=now,
                )
            )

    if anomalies is not None and not anomalies.empty:
        for _, a in anomalies.iterrows():
            if str(a.get("severity")) in ("ELEVATED", "HIGH"):
                rows.append(
                    dict(
                        warning_id=random.randint(10_000_000, 99_999_999),
                        as_of_date=a.get("as_of_date"),
                        region_id=REGION,
                        warning_type=f"CLIMATE_{a.get('metric')}",
                        severity=a.get("severity"),
                        title=f"{a.get('metric')} anomaly {a.get('anomaly_pct')}%",
                        message=(
                            f"Current={a.get('current_value')} vs 30d mean={a.get('mean_30d')}"
                        ),
                        metric_value=float(a.get("anomaly_pct") or 0),
                        confidence_score=float(a.get("confidence_score") or 70),
                        status="OPEN",
                        model_version=MODEL,
                        created_at=now,
                    )
                )
    return pd.DataFrame(rows)


def run():
    logger.info("=== Phase 13 ocean intelligence ===")
    now = datetime.utcnow()
    con = connect()

    ocean = qdf(
        con,
        """
        SELECT date_key, sst_celsius, chlorophyll_mg_m3
        FROM pg.public.fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL OR chlorophyll_mg_m3 IS NOT NULL
        ORDER BY date_key
        """,
    )
    logger.info("Ocean history rows: %s", len(ocean))

    anomalies = build_climate_anomalies(ocean, now)
    write(con, "fact_ocean_climate_anomalies", anomalies)

    fusion = build_fusion(con, anomalies, now)
    write(con, "fact_ocean_risk_fusion", fusion)

    warnings = build_warnings(fusion, anomalies, now)
    write(con, "fact_environmental_warnings", warnings)

    if not fusion.empty:
        f = fusion.iloc[0]
        logger.info(
            "Composite=%s level=%s early=%s | %s",
            f.get("composite_ocean_risk"),
            f.get("risk_level"),
            f.get("early_warning_flag"),
            f.get("drivers"),
        )
    logger.info("Anomalies=%s warnings=%s", len(anomalies), len(warnings))
    logger.info("=== Phase 13 complete ===")


if __name__ == "__main__":
    run()
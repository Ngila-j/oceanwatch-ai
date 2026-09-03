"""
Phase 20 complete — Ocean State Engine.
Combines SST, CHL, tides, bloom, habitat, climate fusion into ocean state,
ecological stress, fisheries conditions, and hazard flags.
"""

import logging
import random
from datetime import datetime

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase20_ocean_state_v1.0"
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


def label_state(score):
    if score is None:
        return "UNKNOWN"
    if score >= 70:
        return "STABLE"
    if score >= 50:
        return "WATCH"
    if score >= 30:
        return "STRESSED"
    return "CRITICAL"


def label_stress(score):
    if score >= 75:
        return "HIGH"
    if score >= 55:
        return "ELEVATED"
    if score >= 35:
        return "WATCH"
    return "LOW"


def label_fish(score):
    if score >= 70:
        return "FAVOURABLE"
    if score >= 50:
        return "MODERATE"
    if score >= 30:
        return "POOR"
    return "UNFAVOURABLE"


def run():
    logger.info("=== Phase 20 Ocean State Engine ===")
    now = datetime.utcnow()
    con = connect()

    oc = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_ocean_conditions
        ORDER BY date_key DESC
        LIMIT 5
        """,
    )
    fus = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_ocean_risk_fusion
        ORDER BY as_of_date DESC
        LIMIT 1
        """,
    )
    hab = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_habitat_suitability
        ORDER BY as_of_date DESC
        LIMIT 1
        """,
    )
    bloom = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_bloom_risk
        ORDER BY risk_date DESC
        LIMIT 1
        """,
    )
    # optional climate anomalies table from phase 13
    anom = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_ocean_climate_anomalies
        ORDER BY date_key DESC
        LIMIT 5
        """,
    )

    sst = chl = tide = None
    if not oc.empty:
        # prefer latest non-null SST/CHL
        for _, r in oc.iterrows():
            if sst is None:
                sst = fnum(r.get("sst_celsius"))
            if chl is None:
                chl = fnum(r.get("chlorophyll_mg_m3"))
            if tide is None:
                tide = fnum(r.get("tide_mean_m"))
            if sst is not None and chl is not None:
                break

    composite = fnum(fus.iloc[0].get("composite_ocean_risk"), 25.0) if not fus.empty else 25.0
    habitat = fnum(hab.iloc[0].get("suitability_score"), 70.0) if not hab.empty else 70.0
    bloom_p = fnum(bloom.iloc[0].get("bloom_probability"), 20.0) if not bloom.empty else 20.0

    climate_anom = 0.0
    if not anom.empty:
        for col in ("anomaly_pct", "anomaly_value", "severity"):
            if col in anom.columns:
                break
        # treat count of non-NORMAL as mild pressure
        if "severity" in anom.columns:
            climate_anom = float((anom["severity"].astype(str).str.upper() != "NORMAL").sum()) * 10.0
        climate_anom = min(40.0, climate_anom)

    # Ocean state: higher is healthier
    state_score = 100.0 - composite * 0.55
    state_score += (habitat - 50.0) * 0.25
    state_score -= bloom_p * 0.15
    state_score -= climate_anom * 0.2
    state_score = max(0.0, min(100.0, state_score))

    ecology = min(100.0, bloom_p * 0.55 + (100.0 - habitat) * 0.35 + climate_anom * 0.2)
    fish_cond = max(
        0.0,
        min(100.0, habitat * 0.55 + (100.0 - bloom_p) * 0.30 + (100.0 - composite) * 0.15),
    )
    # soft signal for port operators (env contribution only)
    port_env = min(100.0, composite * 0.6 + bloom_p * 0.2)

    drivers = (
        f"composite={composite:.1f} | habitat={habitat:.1f} | bloom={bloom_p:.1f} | "
        f"sst={sst} | chl={chl} | climate_anom_pressure={climate_anom:.1f}"
    )
    conf = 82.0 if sst is not None else 65.0
    fresh = 94.0 if sst is not None else 70.0

    state_df = pd.DataFrame(
        [
            dict(
                as_of_date=now.date(),
                region_id=REGION,
                country_id=COUNTRY,
                sst_celsius=sst,
                chlorophyll_mg_m3=chl,
                tide_mean_m=tide,
                ocean_state_score=round(state_score, 1),
                ocean_state_label=label_state(state_score),
                ecology_risk=round(ecology, 1),
                fisheries_condition_score=round(fish_cond, 1),
                port_env_signal=round(port_env, 1),
                drivers=drivers,
                confidence_score=conf,
                freshness_pct=fresh,
                model_version=MODEL,
                created_at=now,
            )
        ]
    )
    write(con, "fact_ocean_state", state_df)

    stress_df = pd.DataFrame(
        [
            dict(
                as_of_date=now.date(),
                region_id=REGION,
                bloom_probability=bloom_p,
                habitat_score=habitat,
                climate_anomaly_score=round(climate_anom, 1),
                stress_score=round(ecology, 1),
                stress_level=label_stress(ecology),
                drivers=drivers,
                model_version=MODEL,
                created_at=now,
            )
        ]
    )
    write(con, "fact_ecological_stress", stress_df)

    fish_df = pd.DataFrame(
        [
            dict(
                as_of_date=now.date(),
                region_id=REGION,
                condition_score=round(fish_cond, 1),
                condition_label=label_fish(fish_cond),
                sst_celsius=sst,
                chlorophyll_mg_m3=chl,
                habitat_score=habitat,
                bloom_probability=bloom_p,
                drivers=drivers,
                model_version=MODEL,
                created_at=now,
            )
        ]
    )
    write(con, "fact_fisheries_conditions", fish_df)

    hazards = []
    if bloom_p >= 60:
        hazards.append(
            dict(
                hazard_id=random.randint(10_000_000, 99_999_999),
                as_of_date=now.date(),
                region_id=REGION,
                hazard_type="BLOOM_RISK",
                severity=label_stress(bloom_p),
                score=bloom_p,
                message=f"Elevated bloom probability {bloom_p:.1f}%",
                model_version=MODEL,
                created_at=now,
            )
        )
    if composite >= 55:
        hazards.append(
            dict(
                hazard_id=random.randint(10_000_000, 99_999_999),
                as_of_date=now.date(),
                region_id=REGION,
                hazard_type="OCEAN_COMPOSITE",
                severity=label_stress(composite),
                score=composite,
                message=f"Ocean risk fusion composite {composite:.1f}",
                model_version=MODEL,
                created_at=now,
            )
        )
    if habitat is not None and habitat < 40:
        hazards.append(
            dict(
                hazard_id=random.randint(10_000_000, 99_999_999),
                as_of_date=now.date(),
                region_id=REGION,
                hazard_type="HABITAT_STRESS",
                severity="WATCH",
                score=100.0 - habitat,
                message=f"Low habitat suitability {habitat:.1f}",
                model_version=MODEL,
                created_at=now,
            )
        )
    if sst is not None and sst >= 30.0:
        hazards.append(
            dict(
                hazard_id=random.randint(10_000_000, 99_999_999),
                as_of_date=now.date(),
                region_id=REGION,
                hazard_type="HIGH_SST",
                severity="WATCH",
                score=sst,
                message=f"SST {sst:.2f}°C above typical comfort band for some species",
                model_version=MODEL,
                created_at=now,
            )
        )
    write(con, "fact_marine_hazards", pd.DataFrame(hazards))

    logger.info(
        "Ocean state=%s %s | ecology=%s | fisheries=%s | hazards=%s",
        round(state_score, 1),
        label_state(state_score),
        round(ecology, 1),
        round(fish_cond, 1),
        len(hazards),
    )
    logger.info("=== Phase 20 complete ===")


if __name__ == "__main__":
    run()
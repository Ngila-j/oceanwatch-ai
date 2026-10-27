"""
Phase 20 — Ocean State Engine.
Fuses SST · chlorophyll · bloom · habitat · climate into ocean state,
ecological stress, fisheries conditions, and hazard flags (Kenya EEZ).

Uses ingestion/.env OCEANWATCH_DB_URI via db_utils. Soft-fails missing facts.
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

MODEL = "phase20_ocean_state_v1.0"
REGION = "kenya_eez"
COUNTRY = "KE"


def connect():
    uri = get_db_uri()
    logger.info("Phase 20 ocean state → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
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
            v = row[c]
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                return v
    return default


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    as_of = now.date()
    con = connect()

    oc = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_ocean_conditions
        ORDER BY date_key DESC NULLS LAST
        LIMIT 10
        """,
    )
    fus = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_ocean_risk_fusion
        ORDER BY as_of_date DESC NULLS LAST
        LIMIT 1
        """,
    )
    hab = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_habitat_suitability
        ORDER BY as_of_date DESC NULLS LAST
        LIMIT 1
        """,
    )
    bloom = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_bloom_risk
        ORDER BY risk_date DESC NULLS LAST
        LIMIT 1
        """,
    )
    anom = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_ocean_climate_anomalies
        ORDER BY date_key DESC NULLS LAST
        LIMIT 5
        """,
    )
    wio = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_wio_intelligence_index
        WHERE region_id = 'kenya_eez'
        ORDER BY index_date DESC NULLS LAST
        LIMIT 3
        """,
    )
    gfw = qdf(
        con,
        """
        SELECT SUM(hours) AS sum_hours, COUNT(*) AS cells
        FROM pg.public.fact_gfw_fishing_effort
        """,
    )

    sst = chl = tide = None
    if not oc.empty:
        for _, r in oc.iterrows():
            if sst is None:
                for k in ("sst_celsius", "sst", "sea_surface_temp", "sst_c"):
                    if k in oc.columns and pd.notna(r.get(k)):
                        sst = fnum(r.get(k))
                        break
            if chl is None:
                for k in ("chlorophyll", "chl_mg_m3", "chlorophyll_a", "chl"):
                    if k in oc.columns and pd.notna(r.get(k)):
                        chl = fnum(r.get(k))
                        break
            if tide is None:
                for k in ("tide_m", "tide_height_m", "sea_level_m"):
                    if k in oc.columns and pd.notna(r.get(k)):
                        tide = fnum(r.get(k))
                        break
            if sst is not None and chl is not None:
                break

    bloom_score = fnum(
        first_val(bloom, ["bloom_risk_score", "risk_score", "score", "bloom_score"]), None
    )
    habitat_score = fnum(
        first_val(hab, ["habitat_score", "suitability_score", "score", "mean_score"]), None
    )
    fusion_ecology = fnum(
        first_val(fus, ["ecology_risk", "ecology_score", "composite_score", "risk_score"]), None
    )
    climate_stress = fnum(
        first_val(anom, ["anomaly_score", "climate_stress", "sst_anomaly", "score"]), None
    )
    ocean_h = fnum(first_val(wio, ["ocean_health_score"]), None)
    fish_p = fnum(first_val(wio, ["fishing_pressure_score"]), None)
    overall_wio = fnum(first_val(wio, ["overall_score"]), None)
    gfw_hours = fnum(first_val(gfw, ["sum_hours"]), None)

    sources = 0
    conf = 40.0
    fresh = 45.0

    # Thermal fit: Kenya nearshore ~26–28°C preferred
    thermal_fit = 55.0
    if sst is not None:
        sources += 1
        conf += 12
        fresh = max(fresh, 80)
        delta = abs(sst - 27.0)
        thermal_fit = clamp(100 - delta * 18)

    productivity = 50.0
    if chl is not None:
        sources += 1
        conf += 10
        fresh = max(fresh, 75)
        # moderate chl supports productivity; very high → bloom stress
        if chl < 0.2:
            productivity = 35.0
        elif chl < 1.0:
            productivity = 70.0
        elif chl < 2.5:
            productivity = 55.0
        else:
            productivity = 30.0

    if bloom_score is not None:
        sources += 1
        conf += 8
        fresh = max(fresh, 70)
    else:
        # proxy from chl
        if chl is not None:
            bloom_score = clamp(min(95, max(5, (chl - 0.5) * 25)))
        else:
            bloom_score = 25.0

    if habitat_score is not None:
        sources += 1
        conf += 8
        fresh = max(fresh, 70)
    else:
        habitat_score = clamp(0.45 * thermal_fit + 0.35 * productivity + 0.20 * (100 - bloom_score))

    if climate_stress is not None:
        sources += 1
        conf += 6
    else:
        climate_stress = clamp(abs((sst or 27) - 27) * 14 + (10 if (chl or 0) > 2 else 0))

    if ocean_h is not None:
        sources += 1
        conf += 8
        fresh = max(fresh, 75)

    if fusion_ecology is not None:
        sources += 1
        conf += 5

    # Ecological stress (higher = worse)
    sst_contrib = clamp(abs((sst or 27) - 27) * 15) if sst is not None else 15.0
    chl_contrib = clamp(max(0, (chl or 0.8) - 1.2) * 20) if chl is not None else 12.0
    bloom_contrib = clamp(bloom_score * 0.55)
    climate_contrib = clamp(climate_stress * 0.45)
    if ocean_h is not None:
        # low health raises stress
        eco_from_wio = clamp(100 - ocean_h)
    else:
        eco_from_wio = None

    stress_score = clamp(
        0.30 * sst_contrib
        + 0.20 * chl_contrib
        + 0.25 * bloom_contrib
        + 0.15 * climate_contrib
        + 0.10 * (eco_from_wio if eco_from_wio is not None else 40)
    )
    if fusion_ecology is not None:
        stress_score = clamp(0.6 * stress_score + 0.4 * fusion_ecology)

    stress_drivers = []
    if sst is not None:
        stress_drivers.append(f"SST={sst:.1f}°C")
    if chl is not None:
        stress_drivers.append(f"CHL={chl:.2f}")
    stress_drivers.append(f"bloom={bloom_score:.0f}")
    if ocean_h is not None:
        stress_drivers.append(f"ocean_health={ocean_h:.0f}")
    if not stress_drivers:
        stress_drivers.append("baseline proxies")

    # Fisheries condition (higher = better)
    pressure_penalty = 0.0
    if fish_p is not None:
        pressure_penalty = clamp(fish_p * 0.35)
        sources += 1
        conf += 5
    elif gfw_hours is not None and gfw_hours > 0:
        pressure_penalty = clamp(min(40, gfw_hours / 10))
        sources += 1

    fish_score = clamp(
        0.35 * thermal_fit
        + 0.30 * habitat_score
        + 0.25 * productivity
        - 0.20 * pressure_penalty
        - 0.15 * (bloom_score * 0.3)
    )

    # Ocean state score (higher = healthier/more stable)
    if ocean_h is not None:
        base_state = ocean_h
    elif overall_wio is not None:
        base_state = overall_wio
    else:
        base_state = clamp(100 - stress_score * 0.85)

    ocean_state = clamp(
        0.40 * base_state
        + 0.25 * thermal_fit
        + 0.20 * habitat_score
        + 0.15 * (100 - bloom_score * 0.5)
        - 0.10 * climate_stress * 0.3
    )
    ecology_risk = clamp(stress_score)

    conf = clamp(conf + min(12, sources * 1.5), 25, 95)
    fresh = clamp(fresh + min(10, sources), 30, 95)

    summary = (
        f"Kenya EEZ ocean state {label_state(ocean_state)} ({ocean_state:.0f}). "
        + (f"SST {sst:.1f}°C. " if sst is not None else "SST n/a. ")
        + (f"CHL {chl:.2f}. " if chl is not None else "")
        + f"Bloom risk {bloom_score:.0f}; habitat {habitat_score:.0f}; "
        f"eco stress {stress_score:.0f} ({label_stress(stress_score)}); "
        f"fisheries {label_fish(fish_score)}. Decision-support only."
    )

    state_df = pd.DataFrame(
        [
            dict(
                as_of_date=as_of,
                region_id=REGION,
                country_id=COUNTRY,
                ocean_state_score=round(ocean_state, 1),
                ocean_state_label=label_state(ocean_state),
                sst_c=round(sst, 2) if sst is not None else None,
                chl_mg_m3=round(chl, 3) if chl is not None else None,
                tide_m=round(tide, 2) if tide is not None else None,
                ecology_risk=round(ecology_risk, 1),
                fisheries_condition_score=round(fish_score, 1),
                bloom_risk_score=round(bloom_score, 1),
                habitat_score=round(habitat_score, 1),
                climate_stress=round(climate_stress, 1),
                confidence_score=round(conf, 1),
                freshness_pct=round(fresh, 1),
                data_sources_count=max(1, sources),
                summary=summary,
                model_version=MODEL,
                created_at=now,
            )
        ]
    )

    stress_df = pd.DataFrame(
        [
            dict(
                as_of_date=as_of,
                region_id=REGION,
                country_id=COUNTRY,
                stress_score=round(stress_score, 1),
                stress_level=label_stress(stress_score),
                drivers="; ".join(stress_drivers),
                sst_contrib=round(sst_contrib, 1),
                chl_contrib=round(chl_contrib, 1),
                bloom_contrib=round(bloom_contrib, 1),
                climate_contrib=round(climate_contrib, 1),
                confidence_score=round(conf, 1),
                model_version=MODEL,
                created_at=now,
            )
        ]
    )

    fish_df = pd.DataFrame(
        [
            dict(
                as_of_date=as_of,
                region_id=REGION,
                country_id=COUNTRY,
                condition_score=round(fish_score, 1),
                condition_label=label_fish(fish_score),
                habitat_score=round(habitat_score, 1),
                thermal_fit=round(thermal_fit, 1),
                productivity_proxy=round(productivity, 1),
                pressure_penalty=round(pressure_penalty, 1),
                confidence_score=round(conf - 5, 1),
                notes=(
                    f"Thermal fit {thermal_fit:.0f}, habitat {habitat_score:.0f}, "
                    f"productivity {productivity:.0f}, pressure penalty {pressure_penalty:.0f}."
                ),
                model_version=MODEL,
                created_at=now,
            )
        ]
    )

    hazards = []

    def add_hazard(htype, severity, score, narrative, source):
        hazards.append(
            dict(
                hazard_id=random.randint(10_000_000, 99_999_999),
                as_of_date=as_of,
                region_id=REGION,
                country_id=COUNTRY,
                hazard_type=htype,
                severity=severity,
                score=round(float(score), 1),
                lat=-4.05,
                lon=39.68,
                narrative=narrative,
                source_table=source,
                model_version=MODEL,
                created_at=now,
            )
        )

    if bloom_score >= 55:
        add_hazard(
            "BLOOM_RISK",
            "HIGH" if bloom_score >= 75 else "WATCH",
            bloom_score,
            f"Elevated bloom-risk proxy ({bloom_score:.0f}) for Kenya EEZ nearshore boxes.",
            "fact_bloom_risk / CHL proxy",
        )
    if sst is not None and abs(sst - 27) >= 2.0:
        add_hazard(
            "THERMAL_STRESS",
            "HIGH" if abs(sst - 27) >= 3 else "WATCH",
            clamp(abs(sst - 27) * 20),
            f"SST {sst:.1f}°C deviates from ~27°C reference — thermal stress watch.",
            "fact_ocean_conditions",
        )
    if stress_score >= 55:
        add_hazard(
            "ECOLOGICAL_STRESS",
            label_stress(stress_score),
            stress_score,
            f"Composite ecological stress {stress_score:.0f} ({label_stress(stress_score)}).",
            "phase20 fusion",
        )
    if climate_stress >= 50:
        add_hazard(
            "CLIMATE_ANOMALY",
            "WATCH",
            climate_stress,
            f"Climate/anomaly stress proxy {climate_stress:.0f}.",
            "fact_ocean_climate_anomalies",
        )
    if not hazards:
        add_hazard(
            "NONE_ACTIVE",
            "INFO",
            10.0,
            "No high-severity marine hazard flags from current inputs.",
            "phase20",
        )

    write(con, "fact_ocean_state", state_df)
    write(con, "fact_ecological_stress", stress_df)
    write(con, "fact_fisheries_conditions", fish_df)
    write(con, "fact_marine_hazards", pd.DataFrame(hazards))

    logger.info(
        "State=%.1f (%s) stress=%.1f fish=%.1f hazards=%s sources=%s",
        ocean_state,
        label_state(ocean_state),
        stress_score,
        fish_score,
        len(hazards),
        sources,
    )
    logger.info("=== Phase 20 complete ===")
    con.close()


if __name__ == "__main__":
    run()

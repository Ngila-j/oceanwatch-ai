"""
Phase 21 — Unified Risk Engine.
Domain scores (PORT / MARITIME / FISHERY / ECOLOGY / WEATHER) + composite
with explicit driver contributions, confidence, and freshness.

Uses ingestion/.env OCEANWATCH_DB_URI via db_utils. Soft-fails missing facts.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import duckdb
import pandas as pd

from db_utils import get_db_uri

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase21_unified_risk_v1.0"
MODEL_NAME = "OceanWatch Unified Risk"
REGION = "kenya_eez"
COUNTRY = "KE"

# Domain weights for composite
WEIGHTS = {
    "PORT": 0.25,
    "MARITIME": 0.25,
    "FISHERY": 0.20,
    "ECOLOGY": 0.15,
    "WEATHER": 0.15,
}


def connect():
    uri = get_db_uri()
    logger.info("Phase 21 risk → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{uri}' AS pg (TYPE POSTGRES)")
    return con


def qdf(con, sql: str) -> pd.DataFrame:
    try:
        return con.execute(sql).fetchdf()
    except Exception as e:  # noqa: BLE001
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


def level(score: float) -> str:
    if score >= 75:
        return "HIGH"
    if score >= 55:
        return "ELEVATED"
    if score >= 35:
        return "MODERATE"
    return "LOW"


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def write(con, table: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        logger.info("%s: 0 rows", table)
        return
    try:
        cols = [
            r[0]
            for r in con.execute(
                """
                SELECT column_name FROM pg.information_schema.columns
                WHERE table_schema = 'public' AND table_name = ?
                ORDER BY ordinal_position
                """,
                [table],
            ).fetchall()
        ]
    except Exception:
        cols = list(df.columns)
    use = [c for c in df.columns if c in cols]
    if not use:
        logger.warning("No matching columns for %s", table)
        return
    con.execute(f"DELETE FROM pg.public.{table}")
    con.register("_risk_df", df[use])
    con.execute(
        f"INSERT INTO pg.public.{table} ({', '.join(use)}) SELECT {', '.join(use)} FROM _risk_df"
    )
    logger.info("%s: %s rows", table, len(df))


def run():
    logger.info("=== Phase 21 Unified Risk Engine ===")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    as_of = now.date()
    con = connect()

    # --- Live signals (all soft-fail) ---
    port = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_port_metrics
        ORDER BY metric_date DESC NULLS LAST LIMIT 3
        """,
    )
    ais = qdf(
        con,
        """
        SELECT COUNT(*) AS n,
               COUNT(DISTINCT mmsi) AS vessels,
               AVG(sog) AS avg_sog
        FROM pg.public.fact_ais_positions
        WHERE event_time > now() - INTERVAL '3 days'
        """,
    )
    gfw = qdf(
        con,
        """
        SELECT AVG(hours) AS avg_hours, SUM(hours) AS sum_hours, COUNT(*) AS cells
        FROM pg.public.fact_gfw_fishing_effort
        """,
    )
    ocean = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_ocean_conditions
        ORDER BY date_key DESC NULLS LAST LIMIT 5
        """,
    )
    wio = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_wio_intelligence_index
        WHERE region_id = 'kenya_eez'
        ORDER BY index_date DESC NULLS LAST LIMIT 3
        """,
    )
    alerts = qdf(
        con,
        """
        SELECT COUNT(*) AS n FROM pg.public.fact_alerts
        WHERE created_at > now() - INTERVAL '7 days'
        """,
    )
    anomalies = qdf(
        con,
        """
        SELECT COUNT(*) AS n FROM pg.public.fact_anomalies
        WHERE detected_at > now() - INTERVAL '7 days'
        """,
    )

    cong = fnum(first_val(port, ["congestion_index", "congestion", "port_congestion"]), None)
    dwell = fnum(first_val(port, ["avg_dwell_hours", "dwell_hours", "avg_wait_hours"]), None)
    arrivals = fnum(first_val(port, ["arrivals", "vessel_arrivals"]), None)

    vessels = fnum(first_val(ais, ["vessels"]), 0.0) or 0.0
    ais_n = fnum(first_val(ais, ["n"]), 0.0) or 0.0
    avg_sog = fnum(first_val(ais, ["avg_sog"]), None)

    gfw_hours = fnum(first_val(gfw, ["sum_hours"]), None)
    gfw_cells = fnum(first_val(gfw, ["cells"]), 0.0) or 0.0

    sst = fnum(first_val(ocean, ["sst_celsius", "sst", "sea_surface_temp"]), None)
    chl = fnum(first_val(ocean, ["chlorophyll", "chl_mg_m3", "chlorophyll_a"]), None)

    overall_wio = fnum(first_val(wio, ["overall_score"]), None)
    fish_p = fnum(first_val(wio, ["fishing_pressure_score"]), None)
    ocean_h = fnum(first_val(wio, ["ocean_health_score"]), None)

    alert_n = fnum(first_val(alerts, ["n"]), 0.0) or 0.0
    anom_n = fnum(first_val(anomalies, ["n"]), 0.0) or 0.0

    drivers_rows = []
    domain_rows = []
    sources = 0

    def add_driver(domain, name, contrib, direction, detail):
        drivers_rows.append(
            dict(
                as_of_date=as_of,
                region_id=REGION,
                domain=domain,
                driver_name=name,
                contribution=round(float(contrib), 2),
                direction=direction,
                detail=detail,
                model_version=MODEL,
                created_at=now,
            )
        )

    def add_domain(domain, score, conf, fresh, n_src, driver_txt):
        domain_rows.append(
            dict(
                as_of_date=as_of,
                region_id=REGION,
                country_id=COUNTRY,
                domain=domain,
                risk_score=round(float(score), 1),
                risk_level=level(score),
                confidence_score=round(float(conf), 1),
                freshness_pct=round(float(fresh), 1),
                data_sources_count=int(n_src),
                drivers=driver_txt,
                model_version=MODEL,
                created_at=now,
            )
        )

    # --- PORT ---
    port_score = 35.0
    port_conf = 40.0
    port_fresh = 50.0
    port_src = 0
    port_bits = []
    if cong is not None:
        # congestion 0-100-ish → risk
        port_score = clamp(20 + cong * 0.7)
        port_conf += 25
        port_fresh = 85
        port_src += 1
        sources += 1
        port_bits.append(f"congestion={cong:.0f}")
        add_driver("PORT", "congestion_index", cong * 0.45, "up", f"Port congestion index {cong:.1f}")
    if dwell is not None:
        port_score = clamp(port_score + min(20, dwell / 4))
        port_conf += 10
        port_src += 1
        port_bits.append(f"dwell={dwell:.0f}h")
        add_driver("PORT", "avg_dwell", min(25, dwell / 3), "up", f"Average dwell {dwell:.1f} h")
    if arrivals is not None:
        port_conf += 8
        port_src += 1
        port_bits.append(f"arrivals={arrivals:.0f}")
        add_driver("PORT", "arrivals", min(15, arrivals / 5), "neutral", f"Arrivals signal {arrivals}")
    if not port_bits:
        port_bits.append("no port metrics — baseline")
        add_driver("PORT", "baseline", 10, "neutral", "No fact_port_metrics; using baseline risk")
    add_domain("PORT", port_score, min(95, port_conf), port_fresh, max(1, port_src), "; ".join(port_bits))

    # --- MARITIME ---
    mar_score = 30.0
    mar_conf = 35.0
    mar_fresh = 40.0
    mar_src = 0
    mar_bits = []
    if vessels > 0:
        # denser traffic slightly elevates watch posture
        mar_score = clamp(25 + min(35, vessels * 1.2) + min(15, alert_n * 3))
        mar_conf += 30
        mar_fresh = 90
        mar_src += 1
        sources += 1
        mar_bits.append(f"vessels={int(vessels)}")
        add_driver(
            "MARITIME",
            "ais_vessel_count",
            min(30, vessels * 0.8),
            "up" if vessels > 20 else "neutral",
            f"{int(vessels)} distinct AIS vessels (3d), {int(ais_n)} positions",
        )
    if avg_sog is not None:
        mar_conf += 8
        mar_src += 1
        mar_bits.append(f"avg_sog={avg_sog:.1f}")
        add_driver("MARITIME", "avg_sog", min(12, abs(avg_sog - 8)), "neutral", f"Mean SOG {avg_sog:.1f} kn")
    if alert_n:
        mar_score = clamp(mar_score + min(20, alert_n * 4))
        mar_bits.append(f"alerts={int(alert_n)}")
        add_driver("MARITIME", "recent_alerts", min(25, alert_n * 3), "up", f"{int(alert_n)} alerts (7d)")
        mar_src += 1
        sources += 1
    if not mar_bits:
        mar_bits.append("no AIS — baseline")
        add_driver("MARITIME", "baseline", 8, "neutral", "No recent AIS; baseline maritime risk")
    add_domain("MARITIME", mar_score, min(95, mar_conf), mar_fresh, max(1, mar_src), "; ".join(mar_bits))

    # --- FISHERY ---
    fish_score = 32.0
    fish_conf = 35.0
    fish_fresh = 45.0
    fish_src = 0
    fish_bits = []
    if fish_p is not None:
        # WIO fishing pressure often higher = more risk/stress
        fish_score = clamp(fish_p)
        fish_conf += 28
        fish_fresh = 80
        fish_src += 1
        sources += 1
        fish_bits.append(f"wio_fish={fish_p:.0f}")
        add_driver("FISHERY", "wio_fishing_pressure", fish_p * 0.5, "up", f"WIO fishing pressure {fish_p:.1f}")
    if gfw_hours is not None and gfw_hours > 0:
        extra = min(25, gfw_hours / 8)
        fish_score = clamp(fish_score + extra * 0.4)
        fish_conf += 15
        fish_fresh = max(fish_fresh, 75)
        fish_src += 1
        sources += 1
        fish_bits.append(f"gfw_h={gfw_hours:.0f}")
        add_driver(
            "FISHERY",
            "gfw_effort_hours",
            extra,
            "up",
            f"GFW effort sum hours {gfw_hours:.1f} across {int(gfw_cells)} cells",
        )
    if not fish_bits:
        fish_bits.append("no fishery signals — baseline")
        add_driver("FISHERY", "baseline", 8, "neutral", "No GFW/WIO fishery inputs")
    add_domain("FISHERY", fish_score, min(95, fish_conf), fish_fresh, max(1, fish_src), "; ".join(fish_bits))

    # --- ECOLOGY ---
    eco_score = 28.0
    eco_conf = 35.0
    eco_fresh = 45.0
    eco_src = 0
    eco_bits = []
    if ocean_h is not None:
        # lower ocean health → higher risk
        eco_score = clamp(100 - ocean_h)
        eco_conf += 25
        eco_fresh = 80
        eco_src += 1
        sources += 1
        eco_bits.append(f"ocean_health={ocean_h:.0f}")
        add_driver(
            "ECOLOGY",
            "wio_ocean_health_inv",
            max(5, 100 - ocean_h) * 0.4,
            "up",
            f"Inverted ocean health {ocean_h:.1f} → eco risk",
        )
    if chl is not None:
        # elevated chl can signal bloom stress
        bump = 0.0
        if chl > 1.5:
            bump = min(25, (chl - 1.5) * 15)
        eco_score = clamp(eco_score + bump)
        eco_conf += 12
        eco_fresh = max(eco_fresh, 70)
        eco_src += 1
        sources += 1
        eco_bits.append(f"chl={chl:.2f}")
        add_driver("ECOLOGY", "chlorophyll", bump or 5, "up" if bump else "neutral", f"Chlorophyll {chl:.3f}")
    if overall_wio is not None and ocean_h is None:
        eco_score = clamp(100 - overall_wio * 0.6)
        eco_conf += 10
        eco_src += 1
        eco_bits.append(f"wio={overall_wio:.0f}")
        add_driver("ECOLOGY", "wio_overall", 10, "neutral", f"WIO overall {overall_wio:.1f}")
    if not eco_bits:
        eco_bits.append("no ecology signals — baseline")
        add_driver("ECOLOGY", "baseline", 7, "neutral", "No ocean/WIO ecology inputs")
    add_domain("ECOLOGY", eco_score, min(95, eco_conf), eco_fresh, max(1, eco_src), "; ".join(eco_bits))

    # --- WEATHER / ocean physical ---
    wx_score = 30.0
    wx_conf = 35.0
    wx_fresh = 45.0
    wx_src = 0
    wx_bits = []
    if sst is not None:
        # thermal stress away from ~27°C Kenya nearshore norm
        delta = abs(sst - 27.0)
        wx_score = clamp(20 + delta * 12)
        wx_conf += 30
        wx_fresh = 85
        wx_src += 1
        sources += 1
        wx_bits.append(f"sst={sst:.1f}C")
        add_driver(
            "WEATHER",
            "sst_anomaly_proxy",
            min(35, delta * 10),
            "up" if delta > 1.5 else "neutral",
            f"SST {sst:.2f}°C (Δ from 27°C = {delta:.2f})",
        )
    if anom_n:
        wx_score = clamp(wx_score + min(15, anom_n * 2))
        wx_bits.append(f"anomalies={int(anom_n)}")
        add_driver("WEATHER", "recent_anomalies", min(15, anom_n * 2), "up", f"{int(anom_n)} anomalies (7d)")
        wx_src += 1
    if not wx_bits:
        wx_bits.append("no SST — baseline")
        add_driver("WEATHER", "baseline", 7, "neutral", "No ocean SST; baseline weather risk")
    add_domain("WEATHER", wx_score, min(95, wx_conf), wx_fresh, max(1, wx_src), "; ".join(wx_bits))

    scores = {
        "PORT": port_score,
        "MARITIME": mar_score,
        "FISHERY": fish_score,
        "ECOLOGY": eco_score,
        "WEATHER": wx_score,
    }
    composite = sum(scores[d] * WEIGHTS[d] for d in WEIGHTS)
    composite = clamp(composite)

    # Confidence / freshness from domains
    confs = [r["confidence_score"] for r in domain_rows]
    freshes = [r["freshness_pct"] for r in domain_rows]
    conf = sum(confs) / len(confs) if confs else 40.0
    fresh = sum(freshes) / len(freshes) if freshes else 40.0
    conf = clamp(conf + min(10, sources))

    top_drivers = sorted(drivers_rows, key=lambda x: -x["contribution"])[:6]
    driver_summary = "; ".join(f"{d['domain']}:{d['driver_name']}={d['contribution']:.0f}" for d in top_drivers)

    composite_row = pd.DataFrame(
        [
            dict(
                as_of_date=as_of,
                region_id=REGION,
                country_id=COUNTRY,
                composite_score=round(composite, 1),
                composite_level=level(composite),
                port_score=round(port_score, 1),
                maritime_score=round(mar_score, 1),
                fishery_score=round(fish_score, 1),
                ecology_score=round(eco_score, 1),
                weather_score=round(wx_score, 1),
                confidence_score=round(conf, 1),
                freshness_pct=round(fresh, 1),
                data_sources_count=max(1, sources),
                drivers=driver_summary,
                model_name=MODEL_NAME,
                model_version=MODEL,
                created_at=now,
            )
        ]
    )

    write(con, "fact_unified_risk", pd.DataFrame(domain_rows))
    write(con, "fact_unified_risk_composite", composite_row)
    write(con, "fact_unified_risk_drivers", pd.DataFrame(drivers_rows))

    logger.info(
        "Composite=%.1f (%s) | PORT=%.0f MAR=%.0f FISH=%.0f ECO=%.0f WX=%.0f | sources=%s",
        composite,
        level(composite),
        port_score,
        mar_score,
        fish_score,
        eco_score,
        wx_score,
        sources,
    )
    logger.info("=== Phase 21 complete ===")
    con.close()


if __name__ == "__main__":
    run()

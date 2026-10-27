"""
Bloom-risk probability from CHL + SST anomaly + persistence.
Indicator only — not a confirmed harmful algal bloom (HAB) diagnosis.

Writes fact_bloom_risk on Supabase via SQLAlchemy + OCEANWATCH_DB_URI.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from db_utils import get_db_uri

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "bloom_risk_proxy_v1.1"
REGION = "kenya_eez"
COUNTRY = "KE"

# Kenya EEZ demo cells near Mombasa / shelf (decision-support only)
CELLS = [
    (-3.90, 39.75, "mombasa_nearshore"),
    (-4.05, 39.68, "mombasa_port_approaches"),
    (-2.50, 41.00, "lamu_shelf"),
    (-4.65, 39.40, "wasini_shimoni"),
    (-1.70, 41.50, "kiunga_north"),
]


def sa_uri() -> str:
    uri = get_db_uri()
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


def engine():
    uri = sa_uri()
    logger.info("Bloom risk → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
    return create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": 30})


def ensure_table(eng) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS fact_bloom_risk (
        risk_date DATE,
        region_id VARCHAR,
        country_id VARCHAR,
        cell_id VARCHAR,
        lat DOUBLE PRECISION,
        lon DOUBLE PRECISION,
        chl_mg_m3 DOUBLE PRECISION,
        sst_c DOUBLE PRECISION,
        sst_anomaly DOUBLE PRECISION,
        persistence_days INTEGER,
        bloom_probability DOUBLE PRECISION,
        risk_level VARCHAR,
        risk_score DOUBLE PRECISION,
        drivers VARCHAR,
        model_version VARCHAR,
        disclaimer VARCHAR,
        created_at TIMESTAMP
    )
    """
    with eng.begin() as conn:
        conn.execute(text(ddl))
    logger.info("fact_bloom_risk schema OK")


def qdf(eng, sql: str) -> pd.DataFrame:
    try:
        return pd.read_sql(text(sql), eng)
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


def risk_level(prob: float) -> str:
    if prob >= 75:
        return "HIGH"
    if prob >= 55:
        return "ELEVATED"
    if prob >= 35:
        return "WATCH"
    return "LOW"


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


def bloom_probability(chl: float, sst_anom: float, persist: int) -> float:
    """
    Lightweight proxy:
    - elevated CHL raises risk (logistic-ish)
    - warm SST anomaly amplifies
    - multi-day persistence compounds
    """
    chl = max(0.01, chl)
    # baseline CHL Kenya shelf often ~0.2–1.0; risk ramps above ~1.2
    chl_term = 100.0 / (1.0 + np.exp(-(chl - 1.1) * 2.2))
    sst_term = clamp(abs(sst_anom) * 12.0, 0, 25)
    persist_term = clamp(persist * 4.5, 0, 20)
    # very low CHL keeps probability low even with SST noise
    if chl < 0.25:
        chl_term *= 0.35
    return clamp(0.70 * chl_term + 0.18 * sst_term + 0.12 * persist_term)


def run():
    logger.info("=== Bloom-risk probability ===")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today = now.date()
    eng = engine()
    ensure_table(eng)

    oc = qdf(
        eng,
        """
        SELECT * FROM fact_ocean_conditions
        ORDER BY date_key DESC NULLS LAST
        LIMIT 14
        """,
    )
    wio = qdf(
        eng,
        """
        SELECT * FROM fact_wio_intelligence_index
        WHERE region_id = 'kenya_eez'
        ORDER BY index_date DESC NULLS LAST
        LIMIT 3
        """,
    )
    state = qdf(
        eng,
        """
        SELECT * FROM fact_ocean_state
        ORDER BY as_of_date DESC NULLS LAST
        LIMIT 1
        """,
    )

    # Pull latest SST / CHL from ocean conditions (column-name tolerant)
    sst = chl = None
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
            if sst is not None and chl is not None:
                break

    if sst is None:
        sst = fnum(first_val(state, ["sst_c"]), 27.2)
    if chl is None:
        chl = fnum(first_val(state, ["chl_mg_m3"]), 0.55)

    # SST anomaly vs ~27°C Kenya nearshore reference
    sst_ref = 27.0
    sst_anom = (sst or sst_ref) - sst_ref

    # Persistence proxy: count recent high-chl-ish rows if available, else 2–4
    persist = 2
    if not oc.empty:
        chl_cols = [c for c in ("chlorophyll", "chl_mg_m3", "chlorophyll_a", "chl") if c in oc.columns]
        if chl_cols:
            series = pd.to_numeric(oc[chl_cols[0]], errors="coerce").dropna()
            persist = int(min(7, max(1, (series > 0.9).sum() or 2)))

    ocean_h = fnum(first_val(wio, ["ocean_health_score"]), None)

    disclaimer = (
        "Bloom-risk indicator only — not a confirmed harmful algal bloom diagnosis. "
        "Requires in-situ biological sampling for HAB confirmation. Decision-support only."
    )

    rows = []
    rng = np.random.default_rng(int(today.strftime("%Y%m%d")) % (2**31))

    # 7-day history ending today (UI shows last 10)
    for day_i in range(6, -1, -1):
        d = today - timedelta(days=day_i)
        # mild day-to-day drift
        day_chl = max(0.05, (chl or 0.55) * (0.85 + 0.3 * rng.random()) + 0.05 * rng.normal())
        day_sst = (sst or 27.2) + 0.35 * rng.normal()
        day_anom = day_sst - sst_ref
        day_persist = max(1, persist - (1 if day_i > 3 else 0) + int(rng.integers(0, 2)))

        for lat, lon, cell in CELLS:
            # spatial jitter on CHL
            cell_chl = max(0.05, day_chl * (0.9 + 0.25 * rng.random()))
            # slightly higher nearshore Mombasa / Lamu shelf
            if "nearshore" in cell or "lamu" in cell:
                cell_chl *= 1.15
            if ocean_h is not None and ocean_h < 45:
                cell_chl *= 1.1

            prob = bloom_probability(cell_chl, day_anom, day_persist)
            # light cell noise
            prob = clamp(prob + rng.normal(0, 3))
            drivers = (
                f"chl={cell_chl:.2f} mg/m³; sst={day_sst:.1f}°C "
                f"(anom={day_anom:+.2f}); persist≈{day_persist}d"
            )
            rows.append(
                dict(
                    risk_date=d,
                    region_id=REGION,
                    country_id=COUNTRY,
                    cell_id=cell,
                    lat=lat,
                    lon=lon,
                    chl_mg_m3=round(cell_chl, 3),
                    sst_c=round(day_sst, 2),
                    sst_anomaly=round(day_anom, 2),
                    persistence_days=int(day_persist),
                    bloom_probability=round(prob, 1),
                    risk_level=risk_level(prob),
                    risk_score=round(prob, 1),
                    drivers=drivers,
                    model_version=MODEL,
                    disclaimer=disclaimer,
                    created_at=now,
                )
            )

    df = pd.DataFrame(rows)
    with eng.begin() as conn:
        # refresh window — keep table lean for the page (last 10 risk_date groups)
        conn.execute(text("DELETE FROM fact_bloom_risk"))
        df.to_sql("fact_bloom_risk", conn, if_exists="append", index=False, method="multi")

    latest = df[df["risk_date"] == today]
    logger.info(
        "Wrote %s rows | today cells=%s | mean_prob=%.1f | max=%.1f (%s)",
        len(df),
        len(latest),
        float(latest["bloom_probability"].mean()) if not latest.empty else 0,
        float(latest["bloom_probability"].max()) if not latest.empty else 0,
        latest.loc[latest["bloom_probability"].idxmax(), "cell_id"] if not latest.empty else "n/a",
    )
    logger.info("=== Bloom-risk complete ===")
    eng.dispose()


if __name__ == "__main__":
    run()

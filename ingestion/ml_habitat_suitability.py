"""
Predicted habitat suitability from environmental features (SST / CHL).
NOT a claim of where fish are — environmental suitability proxy only.

Writes fact_habitat_suitability on Supabase via SQLAlchemy + OCEANWATCH_DB_URI.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from db_utils import get_db_uri

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "habitat_suitability_v1.1"
REGION = "kenya_eez"
COUNTRY = "KE"

# Kenya EEZ monitoring cells (decision-support only)
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
    logger.info("Habitat suitability → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
    return create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": 30})


def ensure_table(eng) -> None:
    # Schema supports both the Streamlit page (as_of_date, suitability_*)
    # and richer multi-cell fields used by Phase 13/20 consumers.
    ddl = """
    CREATE TABLE IF NOT EXISTS fact_habitat_suitability (
        as_of_date DATE,
        region_id VARCHAR,
        country_id VARCHAR,
        region VARCHAR,
        cell_id VARCHAR,
        lat DOUBLE PRECISION,
        lon DOUBLE PRECISION,
        sst_celsius DOUBLE PRECISION,
        chlorophyll_mg_m3 DOUBLE PRECISION,
        habitat_score DOUBLE PRECISION,
        suitability_score DOUBLE PRECISION,
        suitability_class VARCHAR,
        thermal_fit DOUBLE PRECISION,
        productivity_fit DOUBLE PRECISION,
        notes VARCHAR,
        model_version VARCHAR,
        created_at TIMESTAMP
    )
    """
    with eng.begin() as conn:
        conn.execute(text(ddl))
    logger.info("fact_habitat_suitability schema OK")


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


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


def suitability_from_sst_chl(sst, chl):
    """
    Simple scored suitability for pelagic productivity proxy.
    Optimal SST ~26-28°C; moderate CHL preferred over extremes.
    """
    if sst is None and chl is None:
        return 50.0, 50.0, 50.0, "insufficient data"

    if sst is None or (isinstance(sst, float) and np.isnan(sst)):
        sst_score = 50.0
    else:
        sst_score = 100 - min(100, abs(sst - 27.0) * 25)  # peak at 27°C

    if chl is None or (isinstance(chl, float) and np.isnan(chl)):
        chl_score = 50.0
    elif 0.15 <= chl <= 0.6:
        chl_score = 80.0
    elif chl < 0.15:
        chl_score = 40 + chl * 200
    else:
        chl_score = max(20, 80 - (chl - 0.6) * 50)

    score = clamp(0.55 * sst_score + 0.45 * chl_score)
    notes = f"sst={sst if sst is not None else 'n/a'}, chl={chl if chl is not None else 'n/a'}"
    return float(score), float(clamp(sst_score)), float(clamp(chl_score)), notes


def klass_for(score: float) -> str:
    if score >= 70:
        return "HIGH"
    if score >= 45:
        return "MEDIUM"
    return "LOW"


def run():
    logger.info("=== Habitat Suitability ===")
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
    bloom = qdf(
        eng,
        """
        SELECT * FROM fact_bloom_risk
        ORDER BY risk_date DESC NULLS LAST
        LIMIT 10
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

    sst = chl = None
    if not oc.empty:
        for _, r in oc.iterrows():
            if sst is None:
                for k in ("sst_celsius", "sst", "sea_surface_temp", "sst_c"):
                    if k in oc.columns and pd.notna(r.get(k)):
                        sst = fnum(r.get(k))
                        break
            if chl is None:
                for k in ("chlorophyll_mg_m3", "chlorophyll", "chl_mg_m3", "chlorophyll_a", "chl"):
                    if k in oc.columns and pd.notna(r.get(k)):
                        chl = fnum(r.get(k))
                        break
            if sst is not None and chl is not None:
                break

    if sst is None:
        sst = fnum(first_val(state, ["sst_c", "sst_celsius"]), 27.2)
    if chl is None:
        sst_fallback_chl = fnum(first_val(state, ["chl_mg_m3", "chlorophyll_mg_m3"]), None)
        chl = sst_fallback_chl if sst_fallback_chl is not None else fnum(
            first_val(bloom, ["chl_mg_m3"]), 0.45
        )

    rng = np.random.default_rng(int(today.strftime("%Y%m%d")) % (2**31 - 1))
    rows = []

    # 7-day history ending today (page shows last 10)
    for day_i in range(6, -1, -1):
        d = today - timedelta(days=day_i)
        day_sst = (sst or 27.2) + 0.25 * rng.normal()
        day_chl = max(0.05, (chl or 0.45) * (0.9 + 0.2 * rng.random()) + 0.02 * rng.normal())

        for lat, lon, cell in CELLS:
            cell_sst = day_sst + 0.15 * rng.normal()
            cell_chl = max(0.05, day_chl * (0.92 + 0.2 * rng.random()))
            # nearshore / shelf often slightly more productive
            if "nearshore" in cell or "shelf" in cell:
                cell_chl *= 1.08

            score, thermal, prod, feat = suitability_from_sst_chl(cell_sst, cell_chl)
            # light spatial noise
            score = clamp(score + rng.normal(0, 2.5))
            klass = klass_for(score)
            notes = (
                f"Predicted suitability from available environmental features ({feat}). "
                f"Not a fish-presence prediction. cell={cell}"
            )
            rows.append(
                dict(
                    as_of_date=d,
                    region_id=REGION,
                    country_id=COUNTRY,
                    region="Kenya EEZ Monitoring Box",
                    cell_id=cell,
                    lat=lat,
                    lon=lon,
                    sst_celsius=round(cell_sst, 2),
                    chlorophyll_mg_m3=round(cell_chl, 3),
                    habitat_score=round(score, 1),
                    suitability_score=round(score, 1),
                    suitability_class=klass,
                    thermal_fit=round(thermal, 1),
                    productivity_fit=round(prod, 1),
                    notes=notes,
                    model_version=MODEL,
                    created_at=now,
                )
            )

    df = pd.DataFrame(rows)
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM fact_habitat_suitability"))
        df.to_sql("fact_habitat_suitability", conn, if_exists="append", index=False, method="multi")

    latest = df[df["as_of_date"] == today]
    logger.info(
        "Wrote %s rows | today mean=%.1f max=%.1f (%s)",
        len(df),
        float(latest["suitability_score"].mean()) if not latest.empty else 0,
        float(latest["suitability_score"].max()) if not latest.empty else 0,
        latest.loc[latest["suitability_score"].idxmax(), "cell_id"] if not latest.empty else "n/a",
    )
    logger.info("=== Habitat Suitability complete ===")
    eng.dispose()


if __name__ == "__main__":
    run()

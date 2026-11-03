"""
Kenya coastal tide heights + swim windows.

Predicts hourly tide heights for main Kenya coastal stations using a
semi-diurnal harmonic model calibrated to typical WIO ranges (KMFRI-class
order of magnitude). Classifies each hour for recreational swimming:

  FAVOURABLE — depth over reef / mid–high tide, weak current (slack-ish)
  CAUTION    — intermediate height or moderate tidal stream
  RISKY      — low tide (reef/rocks) or strong flood/ebb

Not a substitute for local lifeguard advice, KMFRI official tables, or
surf/current warnings. Re-run daily (or hourly) to roll the forecast window.

Tables:
  fact_coastal_stations
  fact_tide_heights
  fact_swim_windows   (daily rollup per station)
"""

from __future__ import annotations

import logging
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

_INGESTION_DIR = Path(__file__).resolve().parent
if str(_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_INGESTION_DIR))

from db_utils import pg_connection, write_frame  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kenya-tides")

# Angular speeds (degrees per hour)
_OMEGA = {
    "M2": 28.9841042,  # principal lunar semi-diurnal
    "S2": 30.0000000,  # principal solar semi-diurnal
    "N2": 28.4397295,
    "K1": 15.0410686,  # luni-solar diurnal
    "O1": 13.9430356,
}

# Kenya coastal stations — amplitudes (m) and phases (deg) are engineering
# approximations for ops UI, not certified hydrographic predictions.
STATIONS = [
    {
        "station_id": "KE-MSA",
        "station_name": "Mombasa (Kilindini)",
        "zone_id": "KE-MSA",
        "lat": -4.053,
        "lon": 39.668,
        "mean_level_m": 1.70,
        "constituents": {
            "M2": (1.05, 40),
            "S2": (0.42, 55),
            "N2": (0.22, 25),
            "K1": (0.18, 10),
            "O1": (0.10, 350),
        },
        "notes": "Major port; strong streams in channel",
    },
    {
        "station_id": "KE-NYALI",
        "station_name": "Nyali / English Point",
        "zone_id": "KE-MSA",
        "lat": -4.043,
        "lon": 39.695,
        "mean_level_m": 1.65,
        "constituents": {
            "M2": (1.00, 42),
            "S2": (0.40, 57),
            "N2": (0.20, 27),
            "K1": (0.17, 12),
            "O1": (0.09, 352),
        },
        "notes": "Popular swim beaches north of Mombasa",
    },
    {
        "station_id": "KE-DIANI",
        "station_name": "Diani / Ukunda",
        "zone_id": "KE-SHIMONI",
        "lat": -4.280,
        "lon": 39.580,
        "mean_level_m": 1.55,
        "constituents": {
            "M2": (0.95, 45),
            "S2": (0.38, 60),
            "N2": (0.18, 30),
            "K1": (0.16, 15),
            "O1": (0.09, 355),
        },
        "notes": "Reef lagoon — low tide can strand over coral",
    },
    {
        "station_id": "KE-SHIMONI",
        "station_name": "Shimoni / Wasini",
        "zone_id": "KE-SHIMONI",
        "lat": -4.648,
        "lon": 39.381,
        "mean_level_m": 1.50,
        "constituents": {
            "M2": (0.92, 48),
            "S2": (0.36, 62),
            "N2": (0.17, 32),
            "K1": (0.15, 18),
            "O1": (0.08, 0),
        },
        "notes": "South coast channel currents",
    },
    {
        "station_id": "KE-KILIFI",
        "station_name": "Kilifi creek mouth",
        "zone_id": "KE-KILIFI",
        "lat": -3.633,
        "lon": 39.856,
        "mean_level_m": 1.60,
        "constituents": {
            "M2": (0.98, 38),
            "S2": (0.39, 52),
            "N2": (0.19, 22),
            "K1": (0.17, 8),
            "O1": (0.09, 348),
        },
        "notes": "Creek flood/ebb can be strong",
    },
    {
        "station_id": "KE-WATAMU",
        "station_name": "Watamu marine park",
        "zone_id": "KE-KILIFI",
        "lat": -3.362,
        "lon": 40.021,
        "mean_level_m": 1.58,
        "constituents": {
            "M2": (0.96, 36),
            "S2": (0.38, 50),
            "N2": (0.18, 20),
            "K1": (0.16, 6),
            "O1": (0.09, 346),
        },
        "notes": "Reef swimming — prefer rising/high tide",
    },
    {
        "station_id": "KE-MALINDI",
        "station_name": "Malindi",
        "zone_id": "KE-MALINDI",
        "lat": -3.219,
        "lon": 40.117,
        "mean_level_m": 1.62,
        "constituents": {
            "M2": (0.97, 35),
            "S2": (0.39, 49),
            "N2": (0.19, 18),
            "K1": (0.17, 5),
            "O1": (0.09, 344),
        },
        "notes": "Open beach + Sabaki sediment plume",
    },
    {
        "station_id": "KE-LAMU",
        "station_name": "Lamu / Shela",
        "zone_id": "KE-LAMU",
        "lat": -2.272,
        "lon": 40.902,
        "mean_level_m": 1.75,
        "constituents": {
            "M2": (1.10, 30),
            "S2": (0.45, 45),
            "N2": (0.24, 15),
            "K1": (0.20, 0),
            "O1": (0.11, 340),
        },
        "notes": "Channel streams; Shela beach swim windows",
    },
    {
        "station_id": "KE-UNGWANA",
        "station_name": "Ungwana Bay (mid)",
        "zone_id": "KE-UNGWANA",
        "lat": -2.600,
        "lon": 40.500,
        "mean_level_m": 1.68,
        "constituents": {
            "M2": (1.02, 32),
            "S2": (0.41, 47),
            "N2": (0.21, 17),
            "K1": (0.18, 2),
            "O1": (0.10, 342),
        },
        "notes": "Exposed bay; surf + tide interaction",
    },
]


SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS public.fact_coastal_stations (
        station_id    VARCHAR PRIMARY KEY,
        station_name  VARCHAR,
        zone_id       VARCHAR,
        lat           DOUBLE PRECISION,
        lon           DOUBLE PRECISION,
        mean_level_m  DOUBLE PRECISION,
        country_id    VARCHAR DEFAULT 'KE',
        notes         VARCHAR,
        updated_at    TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.fact_tide_heights (
        station_id       VARCHAR NOT NULL,
        ts_utc           TIMESTAMPTZ NOT NULL,
        tide_height_m    DOUBLE PRECISION,
        tide_rate_m_per_h DOUBLE PRECISION,
        stage            VARCHAR,
        swim_rating      VARCHAR,
        swim_reason      VARCHAR,
        is_daylight      BOOLEAN,
        forecast_run_at  TIMESTAMPTZ,
        source           VARCHAR,
        PRIMARY KEY (station_id, ts_utc)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.fact_swim_windows (
        station_id           VARCHAR NOT NULL,
        window_date          DATE NOT NULL,
        favourable_hours     INTEGER,
        caution_hours        INTEGER,
        risky_hours          INTEGER,
        next_favourable_start TIMESTAMPTZ,
        next_favourable_end   TIMESTAMPTZ,
        high_tide_today_m    DOUBLE PRECISION,
        low_tide_today_m     DOUBLE PRECISION,
        high_tide_at         TIMESTAMPTZ,
        low_tide_at          TIMESTAMPTZ,
        summary              VARCHAR,
        computed_at          TIMESTAMPTZ,
        PRIMARY KEY (station_id, window_date)
    )
    """,
]


def _ensure_schema(con) -> None:
    for stmt in SCHEMA_SQL:
        con.execute(stmt)
    for idx in (
        "CREATE INDEX IF NOT EXISTS idx_tide_ts ON public.fact_tide_heights (ts_utc DESC)",
        "CREATE INDEX IF NOT EXISTS idx_tide_station_ts ON public.fact_tide_heights (station_id, ts_utc)",
        "CREATE INDEX IF NOT EXISTS idx_swim_date ON public.fact_swim_windows (window_date DESC)",
    ):
        try:
            con.execute(idx)
        except Exception:  # noqa: BLE001
            try:
                con.rollback()
            except Exception:  # noqa: BLE001
                pass


def _hours_since_ref(ts: datetime) -> float:
    """Hours since 1990-01-01 UTC (stable harmonic epoch)."""
    ref = datetime(1990, 1, 1, tzinfo=timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (ts - ref).total_seconds() / 3600.0


def predict_height(mean_m: float, constituents: dict, ts: datetime) -> float:
    t_h = _hours_since_ref(ts)
    h = mean_m
    for name, (amp, phase_deg) in constituents.items():
        omega = _OMEGA.get(name)
        if omega is None:
            continue
        h += amp * math.cos(math.radians(omega * t_h + phase_deg))
    return round(h, 3)


def _stage(height: float, mean_m: float, amp_span: float) -> str:
    """Relative stage vs local mean and typical half-range."""
    half = max(0.4, amp_span * 0.5)
    if height >= mean_m + half * 0.55:
        return "HIGH"
    if height <= mean_m - half * 0.55:
        return "LOW"
    if height >= mean_m:
        return "MID_HIGH"
    return "MID_LOW"


def _swim_rating(
    height: float,
    rate: float,
    mean_m: float,
    amp_span: float,
    is_daylight: bool,
) -> tuple[str, str]:
    """
    Kenya reef/lagoon heuristics:
    - Prefer mid-high to high for depth over coral
    - Avoid strong |rate| (channel/creek streams)
    - Low tide → reef exposure / rock risk
    - Night → always at least CAUTION
    """
    half = max(0.4, amp_span * 0.5)
    abs_rate = abs(rate)
    low_cut = mean_m - half * 0.45
    high_pref = mean_m + half * 0.15

    if height <= low_cut:
        reason = "Low tide — reef/rocks exposed, shallow swim risk"
        rating = "RISKY"
    elif abs_rate >= 0.45:
        reason = "Strong tidal stream (flood/ebb) — current risk"
        rating = "RISKY"
    elif height >= high_pref and abs_rate <= 0.22:
        reason = "Mid–high tide near slack — favourable depth & weak current"
        rating = "FAVOURABLE"
    elif height >= mean_m - half * 0.1 and abs_rate <= 0.35:
        reason = "Adequate depth; moderate stream — swim with care"
        rating = "CAUTION"
    else:
        reason = "Transitional tide stage — reduced margin over reef"
        rating = "CAUTION"

    if not is_daylight and rating == "FAVOURABLE":
        rating = "CAUTION"
        reason = "Night hours — treat as caution even if tide is good"
    elif not is_daylight and rating == "CAUTION":
        reason = "Night + transitional tide — elevated risk"

    return rating, reason


def _is_daylight(ts: datetime, lat: float) -> bool:
    """Rough tropical daylight ~06:00–18:30 local (UTC+3 Kenya)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    local = ts + timedelta(hours=3)
    minutes = local.hour * 60 + local.minute
    # slight seasonal ignore; Kenya near equator
    return 6 * 60 <= minutes <= 18 * 60 + 30


def _amp_span(constituents: dict) -> float:
    return 2.0 * sum(amp for amp, _ in constituents.values())


def build_forecast(
    hours_back: int = 6,
    hours_forward: int = 72,
    step_minutes: int = 60,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=hours_back)
    end = now + timedelta(hours=hours_forward)
    step = timedelta(minutes=step_minutes)

    station_rows = []
    tide_rows = []

    for stn in STATIONS:
        span = _amp_span(stn["constituents"])
        station_rows.append(
            {
                "station_id": stn["station_id"],
                "station_name": stn["station_name"],
                "zone_id": stn["zone_id"],
                "lat": stn["lat"],
                "lon": stn["lon"],
                "mean_level_m": stn["mean_level_m"],
                "country_id": "KE",
                "notes": stn["notes"],
                "updated_at": now,
            }
        )
        ts = start
        prev_h = None
        while ts <= end:
            h = predict_height(stn["mean_level_m"], stn["constituents"], ts)
            if prev_h is None:
                # estimate rate from +1h
                h2 = predict_height(
                    stn["mean_level_m"],
                    stn["constituents"],
                    ts + timedelta(hours=1),
                )
                rate = round(h2 - h, 3)
            else:
                rate = round(h - prev_h, 3)
            daylight = _is_daylight(ts, stn["lat"])
            stage = _stage(h, stn["mean_level_m"], span)
            rating, reason = _swim_rating(
                h, rate, stn["mean_level_m"], span, daylight
            )
            tide_rows.append(
                {
                    "station_id": stn["station_id"],
                    "ts_utc": ts,
                    "tide_height_m": h,
                    "tide_rate_m_per_h": rate,
                    "stage": stage,
                    "swim_rating": rating,
                    "swim_reason": reason,
                    "is_daylight": daylight,
                    "forecast_run_at": now,
                    "source": "harmonic_v1_kenya",
                }
            )
            prev_h = h
            ts += step

    tides = pd.DataFrame(tide_rows)
    stations = pd.DataFrame(station_rows)

    # daily swim windows (today + next 2 days local)
    window_rows = []
    today_ke = (now + timedelta(hours=3)).date()
    for stn in STATIONS:
        sid = stn["station_id"]
        sub = tides[tides["station_id"] == sid].copy()
        for day_offset in range(0, 3):
            d = today_ke + timedelta(days=day_offset)
            # local day bounds in UTC
            local_start = datetime(d.year, d.month, d.day, 0, 0, tzinfo=timezone.utc) - timedelta(
                hours=3
            )
            local_end = local_start + timedelta(days=1)
            day = sub[(sub["ts_utc"] >= local_start) & (sub["ts_utc"] < local_end)]
            if day.empty:
                continue
            fav = day[day["swim_rating"] == "FAVOURABLE"]
            caut = day[day["swim_rating"] == "CAUTION"]
            risk = day[day["swim_rating"] == "RISKY"]
            # contiguous favourable block starting now or next
            next_start = next_end = None
            if not fav.empty:
                # find first favourable at or after now for today, else first of day
                future_fav = fav[fav["ts_utc"] >= now] if day_offset == 0 else fav
                if future_fav.empty:
                    future_fav = fav
                next_start = future_fav.iloc[0]["ts_utc"]
                # extend while consecutive hours favourable
                t = next_start
                end_t = next_start
                fav_set = set(future_fav["ts_utc"].tolist())
                while t in fav_set:
                    end_t = t
                    t = t + timedelta(hours=1)
                next_end = end_t + timedelta(hours=1)

            hi_idx = day["tide_height_m"].idxmax()
            lo_idx = day["tide_height_m"].idxmin()
            hi = float(day.loc[hi_idx, "tide_height_m"])
            lo = float(day.loc[lo_idx, "tide_height_m"])
            summary = (
                f"{len(fav)}h favourable / {len(caut)}h caution / {len(risk)}h risky · "
                f"HW {hi:.2f}m LW {lo:.2f}m"
            )
            window_rows.append(
                {
                    "station_id": sid,
                    "window_date": d,
                    "favourable_hours": int(len(fav)),
                    "caution_hours": int(len(caut)),
                    "risky_hours": int(len(risk)),
                    "next_favourable_start": next_start,
                    "next_favourable_end": next_end,
                    "high_tide_today_m": hi,
                    "low_tide_today_m": lo,
                    "high_tide_at": day.loc[hi_idx, "ts_utc"],
                    "low_tide_at": day.loc[lo_idx, "ts_utc"],
                    "summary": summary,
                    "computed_at": now,
                }
            )

    return stations, tides, pd.DataFrame(window_rows)


def _enrich_spatial(con, tides: pd.DataFrame, stations: pd.DataFrame, now: datetime) -> None:
    """Attach current tide + swim rating onto today's spatial_intelligence rows."""
    if not _table_exists(con, "spatial_intelligence"):
        return
    # ensure columns
    for col, typ in (
        ("tide_height_m", "DOUBLE PRECISION"),
        ("tide_stage", "VARCHAR"),
        ("swim_rating", "VARCHAR"),
        ("next_favourable_start", "TIMESTAMPTZ"),
    ):
        try:
            con.execute(
                f"ALTER TABLE public.spatial_intelligence ADD COLUMN IF NOT EXISTS {col} {typ}"
            )
        except Exception:  # noqa: BLE001
            try:
                con.rollback()
            except Exception:  # noqa: BLE001
                pass
            try:
                # probe then add without IF NOT EXISTS
                exists = con.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='spatial_intelligence'
                      AND column_name=%s
                    """,
                    (col,),
                ).fetchone()
                if not exists:
                    con.execute(
                        f"ALTER TABLE public.spatial_intelligence ADD COLUMN {col} {typ}"
                    )
            except Exception:  # noqa: BLE001
                try:
                    con.rollback()
                except Exception:  # noqa: BLE001
                    pass

    # nearest hour per zone (pick primary station per zone)
    zone_station = {
        "KE-MSA": "KE-MSA",
        "KE-SHIMONI": "KE-DIANI",
        "KE-KILIFI": "KE-KILIFI",
        "KE-MALINDI": "KE-MALINDI",
        "KE-LAMU": "KE-LAMU",
        "KE-UNGWANA": "KE-UNGWANA",
    }
    hour = now.replace(minute=0, second=0, microsecond=0)
    for zone_id, sid in zone_station.items():
        sub = tides[tides["station_id"] == sid].copy()
        if sub.empty:
            continue
        row = sub[sub["ts_utc"] == hour]
        if row.empty:
            # nearest timestamp
            sub = sub.assign(
                _dt=(pd.to_datetime(sub["ts_utc"], utc=True) - pd.Timestamp(hour, tz="UTC")).abs()
            )
            row = sub.nsmallest(1, "_dt")
        if row.empty:
            continue
        r = row.iloc[0]
        # next favourable from swim windows table path — compute quick
        fav = tides[
            (tides["station_id"] == sid)
            & (tides["ts_utc"] >= hour)
            & (tides["swim_rating"] == "FAVOURABLE")
        ]
        nfs = fav.iloc[0]["ts_utc"] if not fav.empty else None
        try:
            con.execute(
                """
                UPDATE public.spatial_intelligence
                SET tide_height_m = %s,
                    tide_stage = %s,
                    swim_rating = %s,
                    next_favourable_start = %s
                WHERE zone_id = %s
                  AND as_of = (
                    SELECT MAX(as_of) FROM public.spatial_intelligence s2
                    WHERE s2.zone_id = %s
                  )
                """,
                (
                    float(r["tide_height_m"]),
                    str(r["stage"]),
                    str(r["swim_rating"]),
                    nfs,
                    zone_id,
                    zone_id,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("spatial tide update %s: %s", zone_id, exc)
            try:
                con.rollback()
            except Exception:  # noqa: BLE001
                pass


def _table_exists(con, name: str) -> bool:
    try:
        return bool(
            con.execute(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=%s
                """,
                (name,),
            ).fetchone()
        )
    except Exception:  # noqa: BLE001
        try:
            con.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


def _seed_freshness(con, now: datetime) -> None:
    if not _table_exists(con, "data_freshness"):
        return
    try:
        con.execute(
            """
            INSERT INTO public.data_freshness (
              source_key, source_name, last_success_at, age_minutes,
              status, expected_cadence, notes, updated_at
            ) VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (source_key) DO UPDATE SET
              last_success_at = EXCLUDED.last_success_at,
              age_minutes = EXCLUDED.age_minutes,
              status = EXCLUDED.status,
              notes = EXCLUDED.notes,
              updated_at = EXCLUDED.updated_at
            """,
            (
                "coastal_tides",
                "Kenya coastal tides / swim windows",
                now,
                0.0,
                "OK",
                "hourly",
                "Harmonic forecast for KE swim stations",
                now,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("freshness: %s", exc)
        try:
            con.rollback()
        except Exception:  # noqa: BLE001
            pass


def run() -> None:
    logger.info("=== Kenya coastal tides ===")
    now = datetime.now(timezone.utc)
    stations, tides, windows = build_forecast()
    logger.info(
        "built stations=%s tide_rows=%s windows=%s",
        len(stations),
        len(tides),
        len(windows),
    )
    with pg_connection() as con:
        _ensure_schema(con)
        write_frame(con, "fact_coastal_stations", stations, replace=True)
        # replace rolling forecast window
        try:
            con.execute("DELETE FROM public.fact_tide_heights")
        except Exception:  # noqa: BLE001
            try:
                con.rollback()
            except Exception:  # noqa: BLE001
                pass
        write_frame(con, "fact_tide_heights", tides, replace=False)
        try:
            con.execute("DELETE FROM public.fact_swim_windows")
        except Exception:  # noqa: BLE001
            try:
                con.rollback()
            except Exception:  # noqa: BLE001
                pass
        write_frame(con, "fact_swim_windows", windows, replace=False)
        _enrich_spatial(con, tides, stations, now)
        _seed_freshness(con, now)
        for t in (
            "fact_coastal_stations",
            "fact_tide_heights",
            "fact_swim_windows",
        ):
            n = con.execute(f"SELECT COUNT(*) FROM public.{t}").fetchone()[0]
            logger.info("COUNT %s=%s", t, n)
    logger.info("=== Kenya coastal tides done ===")


if __name__ == "__main__":
    run()

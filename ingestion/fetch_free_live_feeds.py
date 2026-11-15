"""
Fetch free live feeds (no paid APIs) into OceanWatch warehouse.

Sources (no account / free):
  - Open-Meteo Weather  https://open-meteo.com  (no key)
  - Open-Meteo Marine   https://open-meteo.com/en/docs/marine-weather-api
  - USGS Earthquakes    https://earthquake.usgs.gov (no key)

Optional (free tier — set keys in ingestion/.env; we cannot create accounts for you):
  - AISSTREAM_API_KEY   → reuse fetch_ais_realtime.py
  - GFW_API_TOKEN       → existing GFW jobs
  - COPERNICUS_*        → existing ocean jobs

Usage:
  python ingestion/fetch_free_live_feeds.py
  python ingestion/fetch_free_live_feeds.py --init
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db_utils import get_db_uri, sa_uri  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("free_live")

UA = {"User-Agent": "OceanWatchAI/1.0 (maritime decision-support; local ops)"}

# Kenya / WIO focus points
LOCATIONS = [
    {"name": "Mombasa", "lat": -4.0435, "lon": 39.6682},
    {"name": "Lamu", "lat": -2.2717, "lon": 40.9020},
    {"name": "Kisumu", "lat": -0.0917, "lon": 34.7680},
    {"name": "Kenya_EEZ_center", "lat": -3.5, "lon": 41.5},
    {"name": "Zanzibar", "lat": -6.1659, "lon": 39.2026},
    {"name": "Dar_es_Salaam", "lat": -6.7924, "lon": 39.2083},
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _log_run(conn, feed: str, status: str, rows: int, message: str, started: datetime) -> None:
    conn.execute(
        text(
            """
            INSERT INTO fact_live_feed_runs (feed_name, status, rows_upserted, message, started_at, finished_at)
            VALUES (:f, :s, :r, :m, :st, :fn)
            """
        ),
        {
            "f": feed,
            "s": status,
            "r": rows,
            "m": message[:500],
            "st": started,
            "fn": _utcnow(),
        },
    )


def fetch_open_meteo_weather(session: requests.Session, loc: dict[str, Any]) -> dict[str, Any]:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "cloud_cover",
                "pressure_msl",
                "wind_speed_10m",
                "wind_direction_10m",
                "weather_code",
            ]
        ),
        "timezone": "UTC",
        "wind_speed_unit": "ms",
    }
    r = session.get(url, params=params, timeout=45)
    r.raise_for_status()
    return r.json()


def fetch_open_meteo_marine(session: requests.Session, loc: dict[str, Any]) -> dict[str, Any]:
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "current": ",".join(
            [
                "wave_height",
                "wave_direction",
                "wave_period",
                "wind_wave_height",
                "swell_wave_height",
                "swell_wave_direction",
                "swell_wave_period",
                "ocean_current_velocity",
                "ocean_current_direction",
                "sea_surface_temperature",
            ]
        ),
        "timezone": "UTC",
    }
    r = session.get(url, params=params, timeout=45)
    r.raise_for_status()
    return r.json()


def fetch_usgs_quakes(session: requests.Session, days: int = 7) -> dict[str, Any]:
    # Western Indian Ocean bounding box (approx)
    # minLon,minLat,maxLon,maxLat
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson",
        "starttime": (_utcnow().date().fromordinal(_utcnow().date().toordinal() - days)).isoformat(),
        "minmagnitude": 3.5,
        "minlatitude": -25,
        "maxlatitude": 15,
        "minlongitude": 30,
        "maxlongitude": 70,
        "orderby": "time",
        "limit": 200,
    }
    r = session.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def store_weather(engine, payloads: list[tuple[dict, dict]]) -> int:
    n = 0
    with engine.begin() as conn:
        for loc, data in payloads:
            cur = data.get("current") or {}
            obs = cur.get("time")
            try:
                observed = datetime.fromisoformat(str(obs).replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                observed = _utcnow()
            conn.execute(
                text(
                    """
                    INSERT INTO fact_live_weather (
                      source, location, lat, lon, observed_at,
                      temp_c, humidity_pct, wind_ms, wind_dir_deg, precip_mm,
                      pressure_hpa, cloud_pct, weather_code, raw_json
                    ) VALUES (
                      'open-meteo', :loc, :lat, :lon, :obs,
                      :t, :h, :w, :wd, :p, :pr, :c, :wc, CAST(:raw AS jsonb)
                    )
                    """
                ),
                {
                    "loc": loc["name"],
                    "lat": loc["lat"],
                    "lon": loc["lon"],
                    "obs": observed,
                    "t": cur.get("temperature_2m"),
                    "h": cur.get("relative_humidity_2m"),
                    "w": cur.get("wind_speed_10m"),
                    "wd": cur.get("wind_direction_10m"),
                    "p": cur.get("precipitation"),
                    "pr": cur.get("pressure_msl"),
                    "c": cur.get("cloud_cover"),
                    "wc": cur.get("weather_code"),
                    "raw": json.dumps(data)[:8000],
                },
            )
            n += 1
    return n


def store_marine(engine, payloads: list[tuple[dict, dict]]) -> int:
    n = 0
    with engine.begin() as conn:
        for loc, data in payloads:
            cur = data.get("current") or {}
            obs = cur.get("time")
            try:
                observed = datetime.fromisoformat(str(obs).replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                observed = _utcnow()
            conn.execute(
                text(
                    """
                    INSERT INTO fact_live_marine (
                      source, location, lat, lon, observed_at,
                      wave_height_m, wave_period_s, wave_dir_deg,
                      swell_height_m, swell_period_s, swell_dir_deg,
                      wind_wave_m, sea_temp_c, raw_json
                    ) VALUES (
                      'open-meteo-marine', :loc, :lat, :lon, :obs,
                      :wh, :wp, :wd, :sh, :sp, :sd, :ww, :sst, CAST(:raw AS jsonb)
                    )
                    """
                ),
                {
                    "loc": loc["name"],
                    "lat": loc["lat"],
                    "lon": loc["lon"],
                    "obs": observed,
                    "wh": cur.get("wave_height"),
                    "wp": cur.get("wave_period"),
                    "wd": cur.get("wave_direction"),
                    "sh": cur.get("swell_wave_height"),
                    "sp": cur.get("swell_wave_period"),
                    "sd": cur.get("swell_wave_direction"),
                    "ww": cur.get("wind_wave_height"),
                    "sst": cur.get("sea_surface_temperature"),
                    "raw": json.dumps(data)[:8000],
                },
            )
            n += 1
    return n


def store_quakes(engine, geojson: dict[str, Any]) -> int:
    feats = geojson.get("features") or []
    n = 0
    with engine.begin() as conn:
        for f in feats:
            props = f.get("properties") or {}
            geom = f.get("geometry") or {}
            coords = geom.get("coordinates") or [None, None, None]
            eid = str(f.get("id") or props.get("code") or props.get("ids") or "")
            if not eid:
                continue
            t_ms = props.get("time")
            event_time = (
                datetime.fromtimestamp(t_ms / 1000.0, tz=timezone.utc) if t_ms else None
            )
            conn.execute(
                text(
                    """
                    INSERT INTO fact_live_earthquakes (
                      id, source, event_time, lat, lon, depth_km, mag, place, tsunami, url, raw_json
                    ) VALUES (
                      :id, 'USGS', :et, :lat, :lon, :dep, :mag, :place, :tsu, :url, CAST(:raw AS jsonb)
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      mag = EXCLUDED.mag,
                      place = EXCLUDED.place,
                      ingested_at = NOW()
                    """
                ),
                {
                    "id": eid[:120],
                    "et": event_time,
                    "lat": coords[1] if len(coords) > 1 else None,
                    "lon": coords[0] if len(coords) > 0 else None,
                    "dep": coords[2] if len(coords) > 2 else None,
                    "mag": props.get("mag"),
                    "place": props.get("place"),
                    "tsu": props.get("tsunami") or 0,
                    "url": props.get("url"),
                    "raw": json.dumps({"properties": props, "geometry": geom})[:4000],
                },
            )
            n += 1
    return n


def run_all(engine) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update(UA)
    summary: dict[str, Any] = {"feeds": {}}

    # Weather
    started = _utcnow()
    try:
        payloads = []
        for loc in LOCATIONS:
            try:
                payloads.append((loc, fetch_open_meteo_weather(session, loc)))
            except Exception as exc:  # noqa: BLE001
                log.warning("weather %s: %s", loc["name"], exc)
        n = store_weather(engine, payloads)
        with engine.begin() as conn:
            _log_run(conn, "open-meteo-weather", "OK", n, f"{n} locations", started)
        summary["feeds"]["weather"] = {"ok": True, "rows": n}
        log.info("weather rows=%s", n)
    except Exception as exc:  # noqa: BLE001
        with engine.begin() as conn:
            _log_run(conn, "open-meteo-weather", "ERROR", 0, str(exc), started)
        summary["feeds"]["weather"] = {"ok": False, "error": str(exc)}

    # Marine
    started = _utcnow()
    try:
        payloads = []
        # marine makes most sense on coastal points
        coastal = [l for l in LOCATIONS if l["name"] not in ("Kisumu",)]
        for loc in coastal:
            try:
                payloads.append((loc, fetch_open_meteo_marine(session, loc)))
            except Exception as exc:  # noqa: BLE001
                log.warning("marine %s: %s", loc["name"], exc)
        n = store_marine(engine, payloads)
        with engine.begin() as conn:
            _log_run(conn, "open-meteo-marine", "OK", n, f"{n} locations", started)
        summary["feeds"]["marine"] = {"ok": True, "rows": n}
        log.info("marine rows=%s", n)
    except Exception as exc:  # noqa: BLE001
        with engine.begin() as conn:
            _log_run(conn, "open-meteo-marine", "ERROR", 0, str(exc), started)
        summary["feeds"]["marine"] = {"ok": False, "error": str(exc)}

    # USGS
    started = _utcnow()
    try:
        geo = fetch_usgs_quakes(session, days=14)
        n = store_quakes(engine, geo)
        with engine.begin() as conn:
            _log_run(conn, "usgs-earthquakes", "OK", n, "WIO M≥3.5 14d", started)
        summary["feeds"]["earthquakes"] = {"ok": True, "rows": n}
        log.info("earthquake rows=%s", n)
    except Exception as exc:  # noqa: BLE001
        with engine.begin() as conn:
            _log_run(conn, "usgs-earthquakes", "ERROR", 0, str(exc), started)
        summary["feeds"]["earthquakes"] = {"ok": False, "error": str(exc)}

    return summary


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    args = ap.parse_args(argv)
    if args.init:
        from init_kpa_and_live_feeds import main as init_main

        init_main()
    else:
        try:
            from init_kpa_and_live_feeds import main as init_main

            init_main()
        except Exception as exc:  # noqa: BLE001
            log.warning("schema: %s", exc)

    eng = create_engine(sa_uri(get_db_uri()), pool_pre_ping=True, connect_args={"connect_timeout": 30})
    summary = run_all(eng)
    print(json.dumps(summary, indent=2, default=str))
    ok = all(v.get("ok") for v in summary.get("feeds", {}).values()) if summary.get("feeds") else False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

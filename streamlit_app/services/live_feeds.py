"""Read free live feed tables + trigger refresh."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def _resolve_uri() -> str:
    try:
        from db_config import get_db_uri

        return get_db_uri()
    except Exception:  # noqa: BLE001
        pass
    app = Path(__file__).resolve().parents[1]
    if str(app) not in sys.path:
        sys.path.insert(0, str(app))
    try:
        from db_config import get_db_uri

        return get_db_uri()
    except Exception:  # noqa: BLE001
        pass
    ing = Path(__file__).resolve().parents[2] / "ingestion"
    if str(ing) not in sys.path:
        sys.path.insert(0, str(ing))
    from db_utils import get_db_uri as _g  # type: ignore

    return _g()


def _sa_uri(uri: str) -> str:
    u = (uri or "").strip()
    if u.startswith("postgresql+psycopg2://"):
        return u
    if u.startswith("postgres://"):
        return "postgresql+psycopg2://" + u[len("postgres://") :]
    if u.startswith("postgresql://"):
        return "postgresql+psycopg2://" + u[len("postgresql://") :]
    return u


class LiveFeedsService:
    def __init__(self, engine: Optional[Engine] = None):
        self.engine = engine or create_engine(
            _sa_uri(_resolve_uri()),
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=0,
            connect_args={"connect_timeout": 25},
        )
        self._ing = Path(__file__).resolve().parents[2] / "ingestion"
        if str(self._ing) not in sys.path:
            sys.path.insert(0, str(self._ing))

    def qdf(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        try:
            with self.engine.connect() as conn:
                return pd.read_sql(text(sql), conn, params=params or {})
        except Exception:  # noqa: BLE001
            return pd.DataFrame()

    def table_exists(self, name: str) -> bool:
        df = self.qdf(
            """
            SELECT 1 AS ok FROM information_schema.tables
            WHERE table_schema='public' AND table_name=:n LIMIT 1
            """,
            {"n": name},
        )
        return not df.empty

    def latest_weather(self) -> pd.DataFrame:
        if not self.table_exists("fact_live_weather"):
            return pd.DataFrame()
        return self.qdf(
            """
            SELECT DISTINCT ON (location)
              location, lat, lon, observed_at, temp_c, humidity_pct, wind_ms,
              wind_dir_deg, precip_mm, pressure_hpa, cloud_pct, weather_code, source
            FROM fact_live_weather
            ORDER BY location, observed_at DESC NULLS LAST
            """
        )

    def latest_marine(self) -> pd.DataFrame:
        if not self.table_exists("fact_live_marine"):
            return pd.DataFrame()
        return self.qdf(
            """
            SELECT DISTINCT ON (location)
              location, lat, lon, observed_at, wave_height_m, wave_period_s, wave_dir_deg,
              swell_height_m, swell_period_s, swell_dir_deg, wind_wave_m, sea_temp_c, source
            FROM fact_live_marine
            ORDER BY location, observed_at DESC NULLS LAST
            """
        )

    def earthquakes(self, limit: int = 50) -> pd.DataFrame:
        if not self.table_exists("fact_live_earthquakes"):
            return pd.DataFrame()
        return self.qdf(
            """
            SELECT event_time, mag, place, lat, lon, depth_km, tsunami, url, source
            FROM fact_live_earthquakes
            ORDER BY event_time DESC NULLS LAST
            LIMIT :n
            """,
            {"n": limit},
        )

    def run_log(self, limit: int = 30) -> pd.DataFrame:
        if not self.table_exists("fact_live_feed_runs"):
            return pd.DataFrame()
        return self.qdf(
            "SELECT * FROM fact_live_feed_runs ORDER BY finished_at DESC NULLS LAST LIMIT :n",
            {"n": limit},
        )

    def status_cards(self) -> list[dict[str, Any]]:
        cards = []
        w = self.latest_weather()
        m = self.latest_marine()
        q = self.earthquakes(5)
        cards.append(
            {
                "title": "Weather (Open-Meteo)",
                "ok": not w.empty,
                "detail": f"{len(w)} sites" if not w.empty else "No rows — run fetch",
                "free": True,
            }
        )
        cards.append(
            {
                "title": "Marine (Open-Meteo)",
                "ok": not m.empty,
                "detail": f"{len(m)} coastal sites" if not m.empty else "No rows — run fetch",
                "free": True,
            }
        )
        cards.append(
            {
                "title": "Earthquakes (USGS)",
                "ok": not q.empty,
                "detail": f"{len(q)} recent WIO events shown" if not q.empty else "No quakes / not fetched",
                "free": True,
            }
        )
        return cards

    def refresh_free_feeds(self) -> dict[str, Any]:
        try:
            from init_kpa_and_live_feeds import main as init_main

            init_main()
        except Exception:  # noqa: BLE001
            pass
        from fetch_free_live_feeds import run_all

        return run_all(self.engine)

    def free_source_catalog(self) -> list[dict[str, str]]:
        return [
            {
                "name": "Open-Meteo Weather",
                "url": "https://open-meteo.com/",
                "key": "None",
                "use": "Air temp, wind, precip for Mombasa / WIO points",
                "status": "Integrated",
            },
            {
                "name": "Open-Meteo Marine",
                "url": "https://open-meteo.com/en/docs/marine-weather-api",
                "key": "None",
                "use": "Waves, swell, SST near Kenya coast",
                "status": "Integrated",
            },
            {
                "name": "USGS Earthquakes",
                "url": "https://earthquake.usgs.gov/fdsnws/event/1/",
                "key": "None",
                "use": "WIO seismic events (tsunami awareness context)",
                "status": "Integrated",
            },
            {
                "name": "AISStream.io",
                "url": "https://aisstream.io/",
                "key": "Free key (you sign up)",
                "use": "Live AIS positions → fact_ais_positions",
                "status": "fetch_ais_realtime.py — set AISSTREAM_API_KEY",
            },
            {
                "name": "Global Fishing Watch",
                "url": "https://globalfishingwatch.org/our-apis/",
                "key": "Free research token (apply)",
                "use": "Fishing effort",
                "status": "Existing GFW jobs — set GFW_API_TOKEN",
            },
            {
                "name": "Copernicus Marine",
                "url": "https://data.marine.copernicus.eu/",
                "key": "Free account",
                "use": "Ocean physics / bio layers",
                "status": "Existing ocean jobs — set COPERNICUS_*",
            },
            {
                "name": "KPA Shipping Movement",
                "url": "https://kpa.co.ke/ShippingMovement",
                "key": "Manual DOCX upload",
                "use": "14-day vessel list Mombasa",
                "status": "Upload integrated (no public API)",
            },
            {
                "name": "OpenStreetMap / Overpass",
                "url": "https://overpass-api.de/",
                "key": "None (rate-limit)",
                "use": "Ports, harbours, coastline features",
                "status": "Catalogued — optional next",
            },
            {
                "name": "NOAA / ERDDAP",
                "url": "https://coastwatch.pfeg.noaa.gov/erddap/",
                "key": "None",
                "use": "SST / chlorophyll grids",
                "status": "Catalogued — optional next",
            },
            {
                "name": "Met.no Locationforecast",
                "url": "https://api.met.no/weatherapi/locationforecast/2.0/documentation",
                "key": "None (User-Agent required)",
                "use": "Alt weather source",
                "status": "Catalogued — Open-Meteo preferred",
            },
        ]

"""
Vessel Tracking service — Kenya EEZ / WIO.

Primary sources (Phase 12):
  dim_vessels_maritime, fact_vessel_profiles, fact_vessel_track_points,
  fact_geofence_events, fact_vessel_behaviour_scores, dim_geofences

Fallbacks:
  fact_ais_positions, fact_vessel_tracks, fact_vessel_geofence_events,
  fact_vessel_behaviour, fact_vessel_anomalies
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

KE_MIN_LAT, KE_MAX_LAT = -5.5, 2.5
KE_MIN_LON, KE_MAX_LON = 38.5, 45.5
MAP_CENTER = (-1.5, 41.5)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sa_uri(uri: str) -> str:
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    if uri.startswith("postgresql://") and "+psycopg2" not in uri:
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    return uri


@dataclass
class FleetSnapshot:
    vessels: pd.DataFrame = field(default_factory=pd.DataFrame)
    tracks_meta: pd.DataFrame = field(default_factory=pd.DataFrame)
    geofence_events: pd.DataFrame = field(default_factory=pd.DataFrame)
    behaviour: pd.DataFrame = field(default_factory=pd.DataFrame)
    anomalies: pd.DataFrame = field(default_factory=pd.DataFrame)
    geofences: pd.DataFrame = field(default_factory=pd.DataFrame)
    ais_latest: pd.DataFrame = field(default_factory=pd.DataFrame)
    errors: list[str] = field(default_factory=list)

    @property
    def vessel_count(self) -> int:
        if self.vessels is not None and not self.vessels.empty:
            return int(len(self.vessels))
        if self.ais_latest is not None and not self.ais_latest.empty:
            return int(len(self.ais_latest))
        return 0

    @property
    def in_kenya_count(self) -> int:
        df = self.vessels if self.vessels is not None and not self.vessels.empty else self.ais_latest
        if df is None or df.empty:
            return 0
        flagged = 0
        for col in ("in_kenya_eez", "in_kenya_box", "in_box"):
            if col in df.columns:
                flagged = max(
                    flagged,
                    int(pd.Series(df[col]).fillna(False).astype(bool).sum()),
                )
        if flagged:
            return flagged
        lat_c = next((c for c in ("lat", "last_lat", "latitude") if c in df.columns), None)
        lon_c = next((c for c in ("lon", "last_lon", "longitude") if c in df.columns), None)
        if lat_c and lon_c:
            lat = pd.to_numeric(df[lat_c], errors="coerce")
            lon = pd.to_numeric(df[lon_c], errors="coerce")
            m = (
                (lat >= KE_MIN_LAT)
                & (lat <= KE_MAX_LAT)
                & (lon >= KE_MIN_LON)
                & (lon <= KE_MAX_LON)
            )
            return int(m.sum())
        return 0


class VesselTrackingService:
    """Query + assemble vessel tracking views for Streamlit pages."""

    def __init__(self, engine: Optional[Engine] = None, db_uri: Optional[str] = None):
        if engine is not None:
            self.engine = engine
        else:
            uri = db_uri
            if not uri:
                # Prefer ingestion db_utils (loads ingestion/.env + pooler)
                try:
                    import sys
                    from pathlib import Path

                    ing = Path(__file__).resolve().parents[2] / "ingestion"
                    if str(ing) not in sys.path:
                        sys.path.insert(0, str(ing))
                    from db_utils import get_db_uri as _ing_uri  # type: ignore

                    uri = _ing_uri()
                except Exception:  # noqa: BLE001
                    uri = None
                if not uri:
                    raise ValueError("engine or db_uri required")
            self.engine = create_engine(
                _sa_uri(uri),
                pool_pre_ping=True,
                pool_size=2,
                max_overflow=0,
                connect_args={"connect_timeout": 20},
            )
        self._col_cache: dict[str, set[str]] = {}
        self._table_cache: dict[str, bool] = {}

    def qdf(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        try:
            with self.engine.connect() as conn:
                return pd.read_sql(text(sql), conn, params=params or {})
        except Exception as exc:  # noqa: BLE001
            logger.debug("vessel_tracking query failed: %s | %s", exc, sql[:140])
            return pd.DataFrame()

    def table_exists(self, name: str) -> bool:
        if name in self._table_cache:
            return self._table_cache[name]
        df = self.qdf(
            """
            SELECT 1 AS ok
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = :n
            LIMIT 1
            """,
            {"n": name},
        )
        ok = not df.empty
        self._table_cache[name] = ok
        return ok

    def columns(self, table: str) -> set[str]:
        if table in self._col_cache:
            return self._col_cache[table]
        if not self.table_exists(table):
            self._col_cache[table] = set()
            return set()
        df = self.qdf(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :n
            """,
            {"n": table},
        )
        cols = set(df["column_name"].str.lower()) if not df.empty else set()
        self._col_cache[table] = cols
        return cols

    def _normalize_vessel_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        rename = {}
        if "last_lat" in df.columns and "lat" not in df.columns:
            rename["last_lat"] = "lat"
        if "last_lon" in df.columns and "lon" not in df.columns:
            rename["last_lon"] = "lon"
        if "latitude" in df.columns and "lat" not in df.columns:
            rename["latitude"] = "lat"
        if "longitude" in df.columns and "lon" not in df.columns:
            rename["longitude"] = "lon"
        if "last_sog" in df.columns and "sog" not in df.columns:
            rename["last_sog"] = "sog"
        if "last_cog" in df.columns and "cog" not in df.columns:
            rename["last_cog"] = "cog"
        if rename:
            df = df.rename(columns=rename)
        if "mmsi" in df.columns:
            df["mmsi"] = df["mmsi"].astype(str)
        return df

    def list_vessels(
        self,
        *,
        hours: int = 48,
        only_kenya: bool = False,
        vessel_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        """Prefer fact_vessel_profiles (has lat/lon); else dim + AIS; else AIS alone."""
        params: dict[str, Any] = {
            "lim": int(limit),
            "since": _utcnow() - timedelta(hours=int(hours)),
        }
        type_sql = ""
        search_sql = ""
        kenya_sql = ""
        if vessel_type and str(vessel_type).upper() not in ("ALL", ""):
            type_sql = "AND UPPER(COALESCE(vessel_type,'')) = UPPER(:vtype)"
            params["vtype"] = vessel_type
        if search:
            search_sql = (
                "AND (CAST(mmsi AS TEXT) ILIKE :q OR COALESCE(vessel_name,'') ILIKE :q "
                "OR COALESCE(flag,'') ILIKE :q)"
            )
            params["q"] = f"%{search.strip()}%"
        if self.table_exists("fact_vessel_profiles"):
            # profiles table has no flag — leave search without flag if column missing
            pcols = self.columns("fact_vessel_profiles")
            kenya_sql = ""
            if only_kenya:
                if "in_kenya_eez" in pcols:
                    kenya_sql = "AND COALESCE(in_kenya_eez, FALSE) = TRUE"
                elif "in_kenya_box" in pcols:
                    kenya_sql = "AND COALESCE(in_kenya_box, FALSE) = TRUE"
            if "flag" not in pcols and search:
                search_sql = (
                    "AND (CAST(mmsi AS TEXT) ILIKE :q OR COALESCE(vessel_name,'') ILIKE :q)"
                )
            time_filter = ""
            if "last_seen" in pcols:
                time_filter = "AND last_seen >= :since"
            elif "computed_at" in pcols:
                time_filter = "AND computed_at >= :since"
            order = "last_seen DESC NULLS LAST" if "last_seen" in pcols else "computed_at DESC NULLS LAST"
            df = self.qdf(
                f"""
                SELECT *
                FROM fact_vessel_profiles
                WHERE 1=1
                  {time_filter}
                  {kenya_sql}
                  {type_sql}
                  {search_sql}
                ORDER BY {order}
                LIMIT :lim
                """,
                params,
            )
            if not df.empty:
                return self._normalize_vessel_frame(df)

        if self.table_exists("dim_vessels_maritime"):
            dcols = self.columns("dim_vessels_maritime")
            if "flag" not in dcols and search:
                search_sql = (
                    "AND (CAST(mmsi AS TEXT) ILIKE :q OR COALESCE(vessel_name,'') ILIKE :q)"
                )
            # dim has no in_kenya_eez — drop kenya filter
            df = self.qdf(
                f"""
                SELECT *
                FROM dim_vessels_maritime
                WHERE 1=1
                  {type_sql}
                  {search_sql}
                ORDER BY last_seen DESC NULLS LAST
                LIMIT :lim
                """,
                params,
            )
            if not df.empty:
                # join latest AIS coords when possible
                ais = self.latest_ais_positions(
                    hours=max(hours, 72), only_kenya=False, limit=2000
                )
                if not ais.empty and "mmsi" in df.columns:
                    keep = [c for c in ("mmsi", "lat", "lon", "sog", "cog") if c in ais.columns]
                    df = df.merge(ais[keep], on="mmsi", how="left", suffixes=("", "_ais"))
                df = self._normalize_vessel_frame(df)
                if only_kenya and {"lat", "lon"}.issubset(df.columns):
                    lat = pd.to_numeric(df["lat"], errors="coerce")
                    lon = pd.to_numeric(df["lon"], errors="coerce")
                    df = df[
                        (lat >= KE_MIN_LAT)
                        & (lat <= KE_MAX_LAT)
                        & (lon >= KE_MIN_LON)
                        & (lon <= KE_MAX_LON)
                    ]
                return df

        return self.latest_ais_positions(
            hours=hours, only_kenya=only_kenya, limit=limit, search=search
        )

    def latest_ais_positions(
        self,
        *,
        hours: int = 48,
        only_kenya: bool = True,
        limit: int = 500,
        search: Optional[str] = None,
    ) -> pd.DataFrame:
        if not self.table_exists("fact_ais_positions"):
            return pd.DataFrame()

        cols = self.columns("fact_ais_positions")
        if "event_time" in cols:
            time_col = "event_time"
        elif "ts" in cols:
            time_col = "ts"
        elif "timestamp" in cols:
            time_col = "timestamp"
        else:
            return pd.DataFrame()

        name_expr = "vessel_name" if "vessel_name" in cols else "NULL::text AS vessel_name"
        type_expr = "vessel_type" if "vessel_type" in cols else "NULL::text AS vessel_type"
        sog_expr = (
            "sog"
            if "sog" in cols
            else ("speed AS sog" if "speed" in cols else "NULL::double precision AS sog")
        )
        cog_expr = (
            "cog"
            if "cog" in cols
            else ("course AS cog" if "course" in cols else "NULL::double precision AS cog")
        )

        params: dict[str, Any] = {
            "since": _utcnow() - timedelta(hours=int(hours)),
            "lim": int(limit),
            "min_lat": KE_MIN_LAT,
            "max_lat": KE_MAX_LAT,
            "min_lon": KE_MIN_LON,
            "max_lon": KE_MAX_LON,
        }
        box = ""
        if only_kenya and "latitude" in cols and "longitude" in cols:
            box = """
              AND latitude BETWEEN :min_lat AND :max_lat
              AND longitude BETWEEN :min_lon AND :max_lon
            """
        search_sql = ""
        if search:
            search_sql = """
              AND (
                CAST(mmsi AS TEXT) ILIKE :q
                OR COALESCE(vessel_name, '') ILIKE :q
              )
            """
            params["q"] = f"%{search.strip()}%"

        sql = f"""
            SELECT * FROM (
                SELECT DISTINCT ON (mmsi)
                  CAST(mmsi AS TEXT) AS mmsi,
                  {name_expr},
                  {type_expr},
                  latitude AS lat,
                  longitude AS lon,
                  {sog_expr},
                  {cog_expr},
                  {time_col} AS last_seen
                FROM fact_ais_positions
                WHERE {time_col} >= :since
                  {box}
                  {search_sql}
                ORDER BY mmsi, {time_col} DESC NULLS LAST
            ) t
            ORDER BY last_seen DESC NULLS LAST
            LIMIT :lim
        """
        df = self.qdf(sql, params)
        return self._normalize_vessel_frame(df)

    def vessel_track(
        self,
        mmsi: str,
        *,
        hours: int = 72,
        limit: int = 2000,
    ) -> pd.DataFrame:
        mmsi = str(mmsi).strip()
        since = _utcnow() - timedelta(hours=int(hours))
        params = {"m": mmsi, "since": since, "lim": int(limit)}

        # Phase 12 primary (supports ts/lat/lon or event_time/latitude/longitude)
        if self.table_exists("fact_vessel_track_points"):
            tcols = self.columns("fact_vessel_track_points")
            ts_col = (
                "ts"
                if "ts" in tcols
                else ("event_time" if "event_time" in tcols else None)
            )
            lat_col = "lat" if "lat" in tcols else ("latitude" if "latitude" in tcols else None)
            lon_col = "lon" if "lon" in tcols else ("longitude" if "longitude" in tcols else None)
            if ts_col and lat_col and lon_col:
                name_sel = "vessel_name" if "vessel_name" in tcols else "NULL::text AS vessel_name"
                sog_sel = "sog" if "sog" in tcols else "NULL::double precision AS sog"
                cog_sel = "cog" if "cog" in tcols else "NULL::double precision AS cog"
                src_sel = "source" if "source" in tcols else "NULL::text AS source"
                df = self.qdf(
                    f"""
                    SELECT
                      CAST(mmsi AS TEXT) AS mmsi,
                      {name_sel},
                      {ts_col} AS ts,
                      {lat_col} AS lat,
                      {lon_col} AS lon,
                      {sog_sel},
                      {cog_sel},
                      {src_sel}
                    FROM fact_vessel_track_points
                    WHERE CAST(mmsi AS TEXT) = :m
                      AND {ts_col} >= :since
                    ORDER BY {ts_col} ASC
                    LIMIT :lim
                    """,
                    params,
                )
                if not df.empty:
                    return df

        # Alternate name
        if self.table_exists("fact_vessel_tracks"):
            tcols = self.columns("fact_vessel_tracks")
            ts_col = "hour_bucket" if "hour_bucket" in tcols else ("ts" if "ts" in tcols else None)
            lat_col = "lat" if "lat" in tcols else ("latitude" if "latitude" in tcols else None)
            lon_col = "lon" if "lon" in tcols else ("longitude" if "longitude" in tcols else None)
            if ts_col and lat_col and lon_col:
                sog_sel = "sog" if "sog" in tcols else "NULL::double precision AS sog"
                cog_sel = "cog" if "cog" in tcols else "NULL::double precision AS cog"
                df = self.qdf(
                    f"""
                    SELECT
                      CAST(mmsi AS TEXT) AS mmsi,
                      {ts_col} AS ts,
                      {lat_col} AS lat,
                      {lon_col} AS lon,
                      {sog_sel},
                      {cog_sel}
                    FROM fact_vessel_tracks
                    WHERE CAST(mmsi AS TEXT) = :m
                      AND {ts_col} >= :since
                    ORDER BY {ts_col} ASC
                    LIMIT :lim
                    """,
                    params,
                )
                if not df.empty:
                    return df

        if not self.table_exists("fact_ais_positions"):
            return pd.DataFrame()

        cols = self.columns("fact_ais_positions")
        if "event_time" in cols:
            time_col = "event_time"
        elif "ts" in cols:
            time_col = "ts"
        else:
            time_col = "timestamp"
        sog = "sog" if "sog" in cols else ("speed" if "speed" in cols else "NULL::double precision")
        cog = "cog" if "cog" in cols else ("course" if "course" in cols else "NULL::double precision")
        name = "vessel_name" if "vessel_name" in cols else "NULL::text"
        return self.qdf(
            f"""
            SELECT
              CAST(mmsi AS TEXT) AS mmsi,
              {time_col} AS ts,
              latitude AS lat,
              longitude AS lon,
              {sog} AS sog,
              {cog} AS cog,
              {name} AS vessel_name
            FROM fact_ais_positions
            WHERE CAST(mmsi AS TEXT) = :m
              AND {time_col} >= :since
            ORDER BY {time_col} ASC
            LIMIT :lim
            """,
            params,
        )

    def vessel_profile(self, mmsi: str) -> dict[str, Any]:
        mmsi = str(mmsi).strip()
        out: dict[str, Any] = {"mmsi": mmsi}
        for table in ("fact_vessel_profiles", "dim_vessels_maritime"):
            if not self.table_exists(table):
                continue
            df = self.qdf(
                f"SELECT * FROM {table} WHERE CAST(mmsi AS TEXT) = :m LIMIT 1",
                {"m": mmsi},
            )
            if not df.empty:
                out.update(
                    {k: (None if pd.isna(v) else v) for k, v in df.iloc[0].to_dict().items()}
                )
                return out
        ais = self.latest_ais_positions(hours=168, only_kenya=False, limit=5000, search=mmsi)
        if not ais.empty:
            row = ais[ais["mmsi"].astype(str) == mmsi]
            if not row.empty:
                out.update(
                    {k: (None if pd.isna(v) else v) for k, v in row.iloc[0].to_dict().items()}
                )
        return out

    def geofences(self) -> pd.DataFrame:
        if not self.table_exists("dim_geofences"):
            return pd.DataFrame()
        return self.qdf(
            """
            SELECT * FROM dim_geofences
            WHERE COALESCE(active, TRUE) = TRUE
            ORDER BY fence_name
            """
        )

    def geofence_events(
        self,
        *,
        hours: int = 72,
        mmsi: Optional[str] = None,
        limit: int = 300,
    ) -> pd.DataFrame:
        table = None
        for cand in ("fact_geofence_events", "fact_vessel_geofence_events"):
            if self.table_exists(cand):
                table = cand
                break
        if not table:
            return pd.DataFrame()
        cols = self.columns(table)
        tcol = "event_time" if "event_time" in cols else ("ts" if "ts" in cols else "ingested_at")
        params: dict[str, Any] = {
            "since": _utcnow() - timedelta(hours=int(hours)),
            "lim": int(limit),
        }
        mmsi_sql = ""
        if mmsi:
            mmsi_sql = "AND CAST(mmsi AS TEXT) = :m"
            params["m"] = str(mmsi).strip()
        return self.qdf(
            f"""
            SELECT *
            FROM {table}
            WHERE {tcol} >= :since
              {mmsi_sql}
            ORDER BY {tcol} DESC NULLS LAST
            LIMIT :lim
            """,
            params,
        )

    def behaviour(
        self,
        *,
        hours: int = 168,
        mmsi: Optional[str] = None,
        limit: int = 300,
    ) -> pd.DataFrame:
        """Behaviour scores table, else derive from fact_vessel_profiles."""
        table = None
        for cand in ("fact_vessel_behaviour_scores", "fact_vessel_behaviour"):
            if self.table_exists(cand):
                table = cand
                break
        params: dict[str, Any] = {
            "since": _utcnow() - timedelta(hours=int(hours)),
            "lim": int(limit),
        }
        mmsi_sql = ""
        if mmsi:
            mmsi_sql = "AND CAST(mmsi AS TEXT) = :m"
            params["m"] = str(mmsi).strip()

        if table:
            cols = self.columns(table)
            tcol = (
                "window_end"
                if "window_end" in cols
                else ("computed_at" if "computed_at" in cols else "created_at")
            )
            df = self.qdf(
                f"""
                SELECT *
                FROM {table}
                WHERE {tcol} >= :since
                  {mmsi_sql}
                ORDER BY {tcol} DESC NULLS LAST
                LIMIT :lim
                """,
                params,
            )
            if not df.empty:
                return df

        # Fallback: profiles carry behaviour_score / risk_score
        if self.table_exists("fact_vessel_profiles"):
            pcols = self.columns("fact_vessel_profiles")
            tcol = "computed_at" if "computed_at" in pcols else "last_seen"
            risk_expr = (
                "COALESCE(risk_score, behaviour_score)"
                if "risk_score" in pcols and "behaviour_score" in pcols
                else (
                    "risk_score"
                    if "risk_score" in pcols
                    else (
                        "behaviour_score"
                        if "behaviour_score" in pcols
                        else "0::double precision"
                    )
                )
            )
            beh_score_sel = (
                "behaviour_score"
                if "behaviour_score" in pcols
                else f"({risk_expr}) AS behaviour_score"
            )
            beh_level_sel = (
                "behaviour_level"
                if "behaviour_level" in pcols
                else "NULL::text AS behaviour_level"
            )
            loiter_sel = (
                "low_speed_ratio AS loitering_score"
                if "low_speed_ratio" in pcols
                else "0::double precision AS loitering_score"
            )
            mpa_sel = (
                "CASE WHEN COALESCE(mpa_interaction_flag, FALSE) THEN 80 ELSE 0 END AS mpa_score"
                if "mpa_interaction_flag" in pcols
                else "0::double precision AS mpa_score"
            )
            turn_sel = (
                "turn_rate_proxy AS speed_anomaly_score"
                if "turn_rate_proxy" in pcols
                else "0::double precision AS speed_anomaly_score"
            )
            evid_sel = "evidence" if "evidence" in pcols else "NULL::text AS evidence"
            name_sel = "vessel_name" if "vessel_name" in pcols else "NULL::text AS vessel_name"
            vtype_sel = "vessel_type" if "vessel_type" in pcols else "NULL::text AS vessel_type"
            win_sel = "last_seen AS window_end" if "last_seen" in pcols else f"{tcol} AS window_end"
            comp_sel = "computed_at" if "computed_at" in pcols else f"{tcol} AS computed_at"
            return self.qdf(
                f"""
                SELECT
                  CAST(mmsi AS TEXT) AS mmsi,
                  {name_sel},
                  {vtype_sel},
                  ({risk_expr}) AS risk_score,
                  {beh_score_sel},
                  {beh_level_sel},
                  {loiter_sel},
                  {mpa_sel},
                  {turn_sel},
                  0::double precision AS dark_score,
                  {evid_sel},
                  {win_sel},
                  {comp_sel}
                FROM fact_vessel_profiles
                WHERE {tcol} >= :since
                  {mmsi_sql}
                ORDER BY ({risk_expr}) DESC NULLS LAST
                LIMIT :lim
                """,
                params,
            )
        return pd.DataFrame()

    def anomalies(
        self,
        *,
        hours: int = 168,
        mmsi: Optional[str] = None,
        limit: int = 200,
    ) -> pd.DataFrame:
        if not self.table_exists("fact_vessel_anomalies"):
            return pd.DataFrame()
        cols = self.columns("fact_vessel_anomalies")
        tcol = "detected_at" if "detected_at" in cols else ("ts" if "ts" in cols else "created_at")
        params: dict[str, Any] = {
            "since": _utcnow() - timedelta(hours=int(hours)),
            "lim": int(limit),
        }
        mmsi_sql = ""
        if mmsi:
            mmsi_sql = "AND CAST(mmsi AS TEXT) = :m"
            params["m"] = str(mmsi).strip()
        return self.qdf(
            f"""
            SELECT *
            FROM fact_vessel_anomalies
            WHERE {tcol} >= :since
              {mmsi_sql}
            ORDER BY {tcol} DESC NULLS LAST
            LIMIT :lim
            """,
            params,
        )

    def snapshot(
        self,
        *,
        hours: int = 48,
        only_kenya: bool = True,
        search: Optional[str] = None,
        vessel_type: Optional[str] = None,
    ) -> FleetSnapshot:
        errors: list[str] = []
        vessels = self.list_vessels(
            hours=hours,
            only_kenya=only_kenya,
            search=search,
            vessel_type=vessel_type,
        )
        if vessels.empty and not self.table_exists("fact_ais_positions"):
            errors.append(
                "No AIS / vessel tables found — run "
                "`python ingestion/run_vessel_tracking.py`"
            )
        ais_latest = self.latest_ais_positions(hours=hours, only_kenya=only_kenya, limit=500)
        tracks_meta = pd.DataFrame()
        for table in ("fact_vessel_track_points", "fact_vessel_tracks"):
            if not self.table_exists(table):
                continue
            tcols = self.columns(table)
            ts_col = next(
                (
                    c
                    for c in ("ts", "event_time", "hour_bucket", "ingested_at")
                    if c in tcols
                ),
                None,
            )
            if not ts_col:
                continue
            # Prefer time-filtered; fall back to full coverage if clock skew empties window
            tracks_meta = self.qdf(
                f"""
                SELECT CAST(mmsi AS TEXT) AS mmsi,
                       COUNT(*) AS track_points,
                       MIN({ts_col}) AS track_from,
                       MAX({ts_col}) AS track_to
                FROM {table}
                WHERE {ts_col} IS NULL OR {ts_col} >= :since
                GROUP BY 1
                ORDER BY track_to DESC NULLS LAST
                LIMIT 500
                """,
                {"since": _utcnow() - timedelta(hours=max(int(hours), 168))},
            )
            if tracks_meta.empty:
                tracks_meta = self.qdf(
                    f"""
                    SELECT CAST(mmsi AS TEXT) AS mmsi,
                           COUNT(*) AS track_points,
                           MIN({ts_col}) AS track_from,
                           MAX({ts_col}) AS track_to
                    FROM {table}
                    GROUP BY 1
                    ORDER BY track_to DESC NULLS LAST
                    LIMIT 500
                    """
                )
            if not tracks_meta.empty:
                break
        return FleetSnapshot(
            vessels=vessels,
            tracks_meta=tracks_meta,
            geofence_events=self.geofence_events(hours=hours),
            behaviour=self.behaviour(hours=max(hours, 72)),
            anomalies=self.anomalies(hours=max(hours, 72)),
            geofences=self.geofences(),
            ais_latest=ais_latest,
            errors=errors,
        )

    def kpis(self, snap: Optional[FleetSnapshot] = None) -> dict[str, Any]:
        snap = snap or self.snapshot()
        vessels = snap.vessels if snap.vessels is not None else pd.DataFrame()
        n = snap.vessel_count
        in_ke = snap.in_kenya_count
        gf = len(snap.geofence_events) if snap.geofence_events is not None else 0
        beh = snap.behaviour if snap.behaviour is not None else pd.DataFrame()
        high_risk = 0
        if not beh.empty:
            for c in ("risk_score", "anomaly_score", "behaviour_score"):
                if c in beh.columns:
                    high_risk = int((pd.to_numeric(beh[c], errors="coerce").fillna(0) >= 70).sum())
                    break
        if high_risk == 0 and not vessels.empty:
            if "risk_tier" in vessels.columns:
                high_risk = int(
                    vessels["risk_tier"]
                    .astype(str)
                    .str.upper()
                    .isin(["HIGH", "CRITICAL", "ELEVATED"])
                    .sum()
                )
            if high_risk == 0 and "behaviour_level" in vessels.columns:
                high_risk = int(
                    vessels["behaviour_level"]
                    .astype(str)
                    .str.upper()
                    .isin(["HIGH", "ELEVATED", "CRITICAL"])
                    .sum()
                )
            if high_risk == 0 and "risk_score" in vessels.columns:
                high_risk = int(
                    (pd.to_numeric(vessels["risk_score"], errors="coerce").fillna(0) >= 70).sum()
                )
            if high_risk == 0 and "behaviour_score" in vessels.columns:
                high_risk = int(
                    (
                        pd.to_numeric(vessels["behaviour_score"], errors="coerce").fillna(0) >= 70
                    ).sum()
                )
        anom = len(snap.anomalies) if snap.anomalies is not None else 0
        moving = 0
        if not vessels.empty:
            for c in ("sog", "avg_sog", "last_sog", "speed_mean"):
                if c in vessels.columns:
                    moving = int((pd.to_numeric(vessels[c], errors="coerce").fillna(0) >= 1.0).sum())
                    break
        return {
            "vessels": n,
            "in_kenya_eez": in_ke,
            "moving": moving,
            "geofence_events": gf,
            "high_risk_behaviour": high_risk,
            "anomalies": anom,
            "track_vessels": int(len(snap.tracks_meta)) if snap.tracks_meta is not None else 0,
        }

    # ------------------------------------------------------------------
    # Port calls (Mombasa) + GFW layers
    # ------------------------------------------------------------------
    def port_activity(
        self,
        *,
        port_name: str = "Mombasa",
        days: int = 14,
        limit: int = 500,
    ) -> pd.DataFrame:
        if not self.table_exists("fact_port_activity"):
            return pd.DataFrame()
        cols = self.columns("fact_port_activity")
        tcol = "event_time" if "event_time" in cols else ("ts" if "ts" in cols else "created_at")
        port_col = "port_name" if "port_name" in cols else None
        params: dict[str, Any] = {
            "since": _utcnow() - timedelta(days=int(days)),
            "lim": int(limit),
            "port": port_name,
        }
        port_sql = f"AND {port_col} ILIKE :port" if port_col else ""
        return self.qdf(
            f"""
            SELECT *
            FROM fact_port_activity
            WHERE {tcol} >= :since
              {port_sql}
            ORDER BY {tcol} DESC NULLS LAST
            LIMIT :lim
            """,
            params,
        )

    def port_metrics(
        self,
        *,
        port_name: str = "Mombasa",
        days: int = 30,
        limit: int = 60,
    ) -> pd.DataFrame:
        if not self.table_exists("fact_port_metrics"):
            return pd.DataFrame()
        cols = self.columns("fact_port_metrics")
        dcol = "metric_date" if "metric_date" in cols else ("date" if "date" in cols else None)
        if not dcol:
            return self.qdf("SELECT * FROM fact_port_metrics ORDER BY 1 DESC LIMIT :lim", {"lim": limit})
        port_col = "port_name" if "port_name" in cols else None
        params: dict[str, Any] = {
            "since": (_utcnow() - timedelta(days=int(days))).date(),
            "lim": int(limit),
            "port": port_name,
        }
        port_sql = f"AND {port_col} ILIKE :port" if port_col else ""
        return self.qdf(
            f"""
            SELECT *
            FROM fact_port_metrics
            WHERE {dcol} >= :since
              {port_sql}
            ORDER BY {dcol} ASC
            LIMIT :lim
            """,
            params,
        )

    def gfw_effort(
        self,
        *,
        days: int = 30,
        limit: int = 800,
    ) -> pd.DataFrame:
        """Global Fishing Watch effort cells (fact_gfw_fishing_effort or fact_fishing_effort)."""
        table = None
        for cand in ("fact_gfw_fishing_effort", "fact_fishing_effort"):
            if self.table_exists(cand):
                table = cand
                break
        if not table:
            return pd.DataFrame()
        cols = self.columns(table)
        dcol = next((c for c in ("date", "effort_date", "day", "obs_date") if c in cols), None)
        lat_c = next((c for c in ("lat", "latitude", "cell_lat") if c in cols), None)
        lon_c = next((c for c in ("lon", "longitude", "cell_lon") if c in cols), None)
        params: dict[str, Any] = {
            "since": (_utcnow() - timedelta(days=int(days))).date(),
            "lim": int(limit),
            "min_lat": KE_MIN_LAT,
            "max_lat": KE_MAX_LAT,
            "min_lon": KE_MIN_LON,
            "max_lon": KE_MAX_LON,
        }
        where = ["1=1"]
        if dcol:
            where.append(f"{dcol} >= :since")
        if lat_c and lon_c:
            where.append(f"{lat_c} BETWEEN :min_lat AND :max_lat")
            where.append(f"{lon_c} BETWEEN :min_lon AND :max_lon")
        order = f"ORDER BY {dcol} DESC NULLS LAST" if dcol else ""
        return self.qdf(
            f"""
            SELECT * FROM {table}
            WHERE {' AND '.join(where)}
            {order}
            LIMIT :lim
            """,
            params,
        )

    def derive_port_calls_from_ais(
        self,
        *,
        hours: int = 168,
        port: str = "Mombasa",
    ) -> pd.DataFrame:
        """Heuristic arrivals/departures from AIS near Mombasa approaches box."""
        # Mombasa approaches box (aligned with KE_MOMBASA_PORT geofence)
        min_lat, max_lat, min_lon, max_lon = -4.2, -3.9, 39.5, 39.8
        if not self.table_exists("fact_ais_positions"):
            return pd.DataFrame()
        cols = self.columns("fact_ais_positions")
        tcol = "event_time" if "event_time" in cols else ("ts" if "ts" in cols else "timestamp")
        sog = "sog" if "sog" in cols else ("speed" if "speed" in cols else "NULL::double precision")
        name = "vessel_name" if "vessel_name" in cols else "NULL::text"
        vtype = "vessel_type" if "vessel_type" in cols else "NULL::text"
        raw = self.qdf(
            f"""
            SELECT
              CAST(mmsi AS TEXT) AS mmsi,
              {name} AS vessel_name,
              {vtype} AS vessel_type,
              {tcol} AS event_time,
              latitude AS lat,
              longitude AS lon,
              {sog} AS sog
            FROM fact_ais_positions
            WHERE {tcol} >= :since
              AND latitude BETWEEN :min_lat AND :max_lat
              AND longitude BETWEEN :min_lon AND :max_lon
            ORDER BY mmsi, {tcol} ASC
            LIMIT 5000
            """,
            {
                "since": _utcnow() - timedelta(hours=int(hours)),
                "min_lat": min_lat,
                "max_lat": max_lat,
                "min_lon": min_lon,
                "max_lon": max_lon,
            },
        )
        if raw.empty:
            return pd.DataFrame()
        events: list[dict[str, Any]] = []
        for mmsi, g in raw.groupby("mmsi"):
            g = g.sort_values("event_time")
            first, last = g.iloc[0], g.iloc[-1]
            sog_first = float(first["sog"]) if pd.notna(first.get("sog")) else None
            sog_last = float(last["sog"]) if pd.notna(last.get("sog")) else None
            # crude: slow near end → arrival/dwell; speeding up after slow → departure
            if sog_last is not None and sog_last < 1.0:
                etype = "ARRIVAL"
            elif sog_first is not None and sog_first < 1.0 and sog_last is not None and sog_last >= 2.0:
                etype = "DEPARTURE"
            else:
                etype = "IN_PORT_AREA"
            events.append(
                {
                    "port_name": port,
                    "event_type": etype,
                    "mmsi": mmsi,
                    "vessel_name": first.get("vessel_name"),
                    "vessel_type": first.get("vessel_type"),
                    "event_time": last.get("event_time"),
                    "lat": last.get("lat"),
                    "lon": last.get("lon"),
                    "sog": sog_last,
                    "source": "ais_heuristic",
                }
            )
        return pd.DataFrame(events)

    def risk_flags(self, vessels: pd.DataFrame) -> pd.DataFrame:
        """Attach simple risk / anomaly flags for the fleet table."""
        if vessels is None or vessels.empty:
            return pd.DataFrame()
        df = vessels.copy()
        flags: list[str] = []
        for _, r in df.iterrows():
            bits: list[str] = []
            sog = None
            for c in ("sog", "last_sog", "speed_mean"):
                if c in df.columns and pd.notna(r.get(c)):
                    try:
                        sog = float(r[c])
                    except (TypeError, ValueError):
                        sog = None
                    break
            low_ratio = None
            if "low_speed_ratio" in df.columns and pd.notna(r.get("low_speed_ratio")):
                try:
                    low_ratio = float(r["low_speed_ratio"])
                except (TypeError, ValueError):
                    low_ratio = None
            score = None
            for c in ("risk_score", "behaviour_score", "anomaly_score"):
                if c in df.columns and pd.notna(r.get(c)):
                    try:
                        score = float(r[c])
                    except (TypeError, ValueError):
                        score = None
                    break
            tier = str(r.get("risk_tier") or r.get("behaviour_level") or "").upper()
            if sog is not None and sog < 0.5:
                bits.append("LOITER/DWELL")
            if low_ratio is not None and low_ratio >= 0.55:
                bits.append("LOITERING")
            if score is not None and score >= 70:
                bits.append("HIGH_RISK")
            elif score is not None and score >= 45:
                bits.append("WATCH")
            if tier in ("HIGH", "CRITICAL", "ELEVATED"):
                bits.append(tier)
            if bool(r.get("mpa_interaction_flag")):
                bits.append("MPA")
            # "dark" proxy: missing name + low speed in EEZ
            name = str(r.get("vessel_name") or "").strip()
            if (not name or name.upper() in ("UNKNOWN", "NONE", "NAN")) and sog is not None and sog < 1.0:
                bits.append("DARK_CUE")
            flags.append(" · ".join(bits) if bits else "OK")
        df["risk_flags"] = flags
        return df

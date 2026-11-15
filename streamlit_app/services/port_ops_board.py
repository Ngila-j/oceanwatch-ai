"""
Port Ops Board — fused Mombasa picture.

Combines:
  - KPA 14-day shipping movement
  - AIS near-port positions
  - Fuzzy KPA↔AIS vessel match
  - Open-Meteo weather / marine for Mombasa
  - Phase-14 port KPIs when present
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

MOMBASA = {"lat": -4.0435, "lon": 39.6682}
NM_PER_DEG_LAT = 60.0


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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_vessel_name(name: Any) -> str:
    s = str(name or "").upper().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    # drop common prefixes
    for p in ("MV ", "MT ", "MS ", "SS ", "M/V ", "M.V ", "M V "):
        if s.startswith(p.strip()) or s.startswith(p):
            s = s[len(p) :].strip() if s.startswith(p) else re.sub(r"^(MV|MT|MS|SS)\s+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def name_tokens(name: str) -> set[str]:
    stop = {"THE", "OF", "AND", "SHIP", "VESSEL"}
    return {t for t in normalize_vessel_name(name).split() if len(t) > 1 and t not in stop}


def name_similarity(a: str, b: str) -> float:
    """Token Jaccard + containment score in [0, 1]."""
    na, nb = normalize_vessel_name(a), normalize_vessel_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.92
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    j = inter / union if union else 0.0
    # boost if majority of shorter name matched
    shorter = ta if len(ta) <= len(tb) else tb
    cov = inter / len(shorter) if shorter else 0.0
    return max(j, cov * 0.95)


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    km = 2 * r * math.asin(min(1.0, math.sqrt(a)))
    return km / 1.852


@dataclass
class PortOpsPack:
    generated_at: str = ""
    kpis: dict[str, Any] = field(default_factory=dict)
    brief: str = ""
    kpa: pd.DataFrame = field(default_factory=pd.DataFrame)
    ais_near: pd.DataFrame = field(default_factory=pd.DataFrame)
    matches: pd.DataFrame = field(default_factory=pd.DataFrame)
    unmatched_kpa: pd.DataFrame = field(default_factory=pd.DataFrame)
    weather: dict[str, Any] = field(default_factory=dict)
    marine: dict[str, Any] = field(default_factory=dict)
    arrival_board: pd.DataFrame = field(default_factory=pd.DataFrame)
    berth_load: pd.DataFrame = field(default_factory=pd.DataFrame)
    agent_mix: pd.DataFrame = field(default_factory=pd.DataFrame)
    cargo_mix: pd.DataFrame = field(default_factory=pd.DataFrame)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class PortOpsBoardService:
    def __init__(self, engine: Optional[Engine] = None):
        self.engine = engine or create_engine(
            _sa_uri(_resolve_uri()),
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=0,
            connect_args={"connect_timeout": 25},
        )
        self.errors: list[str] = []

    def qdf(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        try:
            with self.engine.connect() as conn:
                return pd.read_sql(text(sql), conn, params=params or {})
        except Exception as exc:  # noqa: BLE001
            self.errors.append(str(exc)[:200])
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

    def columns(self, table: str) -> set[str]:
        df = self.qdf(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t
            """,
            {"t": table},
        )
        if df.empty:
            return set()
        return set(df["column_name"].astype(str).str.lower())

    def load_kpa(self, limit: int = 500) -> pd.DataFrame:
        if not self.table_exists("fact_kpa_shipping_movement"):
            return pd.DataFrame()
        return self.qdf(
            """
            SELECT *
            FROM fact_kpa_shipping_movement
            WHERE report_date = (SELECT MAX(report_date) FROM fact_kpa_shipping_movement)
               OR (report_date IS NULL AND ingested_at > NOW() - INTERVAL '14 days')
            ORDER BY eta NULLS LAST, vessel_name
            LIMIT :lim
            """,
            {"lim": limit},
        )

    def load_ais_near(self, radius_nm: float = 40.0, hours: int = 36, limit: int = 800) -> pd.DataFrame:
        if not self.table_exists("fact_ais_positions"):
            return pd.DataFrame()
        cols = self.columns("fact_ais_positions")
        # flexible column names
        lat_c = next((c for c in ("lat", "latitude", "y") if c in cols), None)
        lon_c = next((c for c in ("lon", "longitude", "lng", "x") if c in cols), None)
        if not lat_c or not lon_c:
            return pd.DataFrame()
        ts_c = next(
            (c for c in ("event_time", "ts", "timestamp", "msg_time", "observed_at", "created_at") if c in cols),
            None,
        )
        name_c = next((c for c in ("vessel_name", "shipname", "name", "ship_name") if c in cols), None)
        mmsi_c = "mmsi" if "mmsi" in cols else None
        sog_c = next((c for c in ("sog", "speed", "speed_knots") if c in cols), None)
        cog_c = next((c for c in ("cog", "course", "heading") if c in cols), None)
        type_c = next((c for c in ("ship_type", "vessel_type", "type_name", "shiptype") if c in cols), None)

        # rough degree box (~1 deg lat ≈ 60 nm)
        dlat = radius_nm / NM_PER_DEG_LAT + 0.15
        dlon = radius_nm / (NM_PER_DEG_LAT * max(0.2, math.cos(math.radians(MOMBASA["lat"])))) + 0.15

        select = [f"{lat_c} AS lat", f"{lon_c} AS lon"]
        if mmsi_c:
            select.append(f"{mmsi_c} AS mmsi")
        if name_c:
            select.append(f"{name_c} AS vessel_name")
        if sog_c:
            select.append(f"{sog_c} AS sog")
        if cog_c:
            select.append(f"{cog_c} AS cog")
        if type_c:
            select.append(f"{type_c} AS ship_type")
        if ts_c:
            select.append(f"{ts_c} AS event_time")

        time_filter = f"AND {ts_c} > NOW() - INTERVAL '{int(hours)} hours'" if ts_c else ""
        order = f"ORDER BY {ts_c} DESC NULLS LAST" if ts_c else ""

        sql = f"""
            SELECT {", ".join(select)}
            FROM fact_ais_positions
            WHERE {lat_c} BETWEEN :lat0 AND :lat1
              AND {lon_c} BETWEEN :lon0 AND :lon1
              {time_filter}
            {order}
            LIMIT :lim
        """
        df = self.qdf(
            sql,
            {
                "lat0": MOMBASA["lat"] - dlat,
                "lat1": MOMBASA["lat"] + dlat,
                "lon0": MOMBASA["lon"] - dlon,
                "lon1": MOMBASA["lon"] + dlon,
                "lim": limit,
            },
        )
        if df.empty:
            return df
        # latest per mmsi
        if "mmsi" in df.columns:
            if "event_time" in df.columns:
                df = df.sort_values("event_time", ascending=False)
            df = df.drop_duplicates(subset=["mmsi"], keep="first")
        # distance
        df["dist_nm"] = df.apply(
            lambda r: haversine_nm(
                float(r["lat"]), float(r["lon"]), MOMBASA["lat"], MOMBASA["lon"]
            )
            if pd.notna(r.get("lat")) and pd.notna(r.get("lon"))
            else None,
            axis=1,
        )
        df = df[df["dist_nm"].isna() | (df["dist_nm"] <= radius_nm)].copy()
        df = df.sort_values("dist_nm", ascending=True)
        return df.reset_index(drop=True)

    def match_kpa_ais(
        self,
        kpa: pd.DataFrame,
        ais: pd.DataFrame,
        min_score: float = 0.55,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        if kpa.empty or ais.empty or "vessel_name" not in kpa.columns:
            return pd.DataFrame(), kpa.copy() if not kpa.empty else pd.DataFrame()

        ais_names = []
        for _, r in ais.iterrows():
            nm = r.get("vessel_name")
            if nm and str(nm).strip():
                ais_names.append(r)

        matches = []
        matched_idx = set()
        for i, kr in kpa.iterrows():
            kn = kr.get("vessel_name")
            if not kn:
                continue
            best = None
            best_s = 0.0
            for ar in ais_names:
                s = name_similarity(str(kn), str(ar.get("vessel_name")))
                if s > best_s:
                    best_s = s
                    best = ar
            if best is not None and best_s >= min_score:
                matched_idx.add(i)
                matches.append(
                    {
                        "kpa_vessel": kn,
                        "ais_vessel": best.get("vessel_name"),
                        "match_score": round(best_s, 3),
                        "mmsi": best.get("mmsi"),
                        "dist_nm": round(float(best["dist_nm"]), 2)
                        if best.get("dist_nm") is not None and pd.notna(best.get("dist_nm"))
                        else None,
                        "sog": best.get("sog"),
                        "eta": kr.get("eta"),
                        "etd": kr.get("etd"),
                        "berth": kr.get("berth"),
                        "agent": kr.get("agent"),
                        "cargo": kr.get("cargo"),
                        "ais_lat": best.get("lat"),
                        "ais_lon": best.get("lon"),
                        "status": self._match_status(best_s, best.get("dist_nm"), best.get("sog")),
                    }
                )
        mdf = pd.DataFrame(matches)
        if not mdf.empty:
            mdf = mdf.sort_values(["match_score", "dist_nm"], ascending=[False, True])
        unmatched = kpa.drop(index=list(matched_idx), errors="ignore")
        return mdf, unmatched

    @staticmethod
    def _match_status(score: float, dist_nm: Any, sog: Any) -> str:
        try:
            d = float(dist_nm) if dist_nm is not None and pd.notna(dist_nm) else 999
        except (TypeError, ValueError):
            d = 999
        try:
            sp = float(sog) if sog is not None and pd.notna(sog) else 0
        except (TypeError, ValueError):
            sp = 0
        if score >= 0.85 and d <= 5:
            return "IN PORT / ALONGSIDE"
        if score >= 0.7 and d <= 15:
            return "NEAR PORT"
        if d <= 25 and sp >= 1:
            return "APPROACHING"
        if score >= 0.55:
            return "AIS MATCH"
        return "WEAK MATCH"

    def load_weather_marine(self) -> tuple[dict[str, Any], dict[str, Any]]:
        weather: dict[str, Any] = {}
        marine: dict[str, Any] = {}
        if self.table_exists("fact_live_weather"):
            df = self.qdf(
                """
                SELECT * FROM fact_live_weather
                WHERE location = 'Mombasa'
                ORDER BY observed_at DESC NULLS LAST
                LIMIT 1
                """
            )
            if not df.empty:
                weather = df.iloc[0].to_dict()
        if self.table_exists("fact_live_marine"):
            df = self.qdf(
                """
                SELECT * FROM fact_live_marine
                WHERE location = 'Mombasa'
                ORDER BY observed_at DESC NULLS LAST
                LIMIT 1
                """
            )
            if not df.empty:
                marine = df.iloc[0].to_dict()
        return weather, marine

    def load_port_kpi_hint(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.table_exists("fact_port_performance"):
            df = self.qdf(
                """
                SELECT * FROM fact_port_performance
                ORDER BY metric_date DESC NULLS LAST
                LIMIT 1
                """
            )
            if not df.empty:
                out = df.iloc[0].to_dict()
        if self.table_exists("fact_port_ops_risk"):
            df = self.qdf(
                "SELECT * FROM fact_port_ops_risk ORDER BY metric_date DESC NULLS LAST LIMIT 1"
            )
            if not df.empty:
                out["ops_risk"] = df.iloc[0].to_dict()
        return out

    def build_arrival_board(self, kpa: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
        if kpa.empty:
            return pd.DataFrame()
        rows = []
        match_map = {}
        if not matches.empty:
            for _, m in matches.iterrows():
                match_map[str(m.get("kpa_vessel") or "").upper()] = m

        now = _utcnow()
        for _, r in kpa.iterrows():
            eta = r.get("eta")
            etd = r.get("etd")
            eta_ts = pd.to_datetime(eta, utc=True, errors="coerce")
            hours_to = None
            if pd.notna(eta_ts):
                hours_to = (eta_ts.to_pydatetime() - now).total_seconds() / 3600.0
            key = str(r.get("vessel_name") or "").upper()
            m = match_map.get(key)
            rows.append(
                {
                    "vessel": r.get("vessel_name"),
                    "eta": eta,
                    "etd": etd,
                    "hours_to_eta": round(hours_to, 1) if hours_to is not None else None,
                    "berth": r.get("berth"),
                    "agent": r.get("agent"),
                    "cargo": r.get("cargo"),
                    "voyage": r.get("voyage"),
                    "ais_match": m.get("ais_vessel") if m is not None else None,
                    "mmsi": m.get("mmsi") if m is not None else None,
                    "dist_nm": m.get("dist_nm") if m is not None else None,
                    "ais_status": m.get("status") if m is not None else "NO AIS",
                    "match_score": m.get("match_score") if m is not None else None,
                }
            )
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        # sort: soonest ETA first, nulls last
        df["_h"] = pd.to_numeric(df["hours_to_eta"], errors="coerce")
        df = df.sort_values("_h", ascending=True, na_position="last").drop(columns="_h")
        return df.reset_index(drop=True)

    def build_alerts(
        self,
        kpa: pd.DataFrame,
        matches: pd.DataFrame,
        marine: dict[str, Any],
        weather: dict[str, Any],
        board: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        if kpa.empty:
            alerts.append(
                {
                    "severity": "WATCH",
                    "title": "No KPA 14-day list loaded",
                    "detail": "Upload DOCX from kpa.co.ke/ShippingMovement",
                }
            )
        wh = marine.get("wave_height_m")
        try:
            if wh is not None and float(wh) >= 2.5:
                alerts.append(
                    {
                        "severity": "HIGH",
                        "title": f"Elevated waves at Mombasa ({float(wh):.1f} m)",
                        "detail": "Marine conditions may affect pilotage / lighterage",
                    }
                )
            elif wh is not None and float(wh) >= 1.8:
                alerts.append(
                    {
                        "severity": "WATCH",
                        "title": f"Moderate seas ({float(wh):.1f} m)",
                        "detail": "Monitor berth operations",
                    }
                )
        except (TypeError, ValueError):
            pass
        wind = weather.get("wind_ms")
        try:
            if wind is not None and float(wind) >= 12:
                alerts.append(
                    {
                        "severity": "WATCH",
                        "title": f"Strong wind {float(wind):.1f} m/s",
                        "detail": "Open-Meteo Mombasa current",
                    }
                )
        except (TypeError, ValueError):
            pass

        if not board.empty and "hours_to_eta" in board.columns:
            soon = board[pd.to_numeric(board["hours_to_eta"], errors="coerce").between(0, 24)]
            if len(soon) >= 8:
                alerts.append(
                    {
                        "severity": "WATCH",
                        "title": f"{len(soon)} KPA arrivals in next 24h",
                        "detail": "Berth pressure likely — cross-check congestion forecast",
                    }
                )
            no_ais = soon[soon["ais_status"] == "NO AIS"] if "ais_status" in soon.columns else soon.head(0)
            if len(no_ais) >= 3:
                alerts.append(
                    {
                        "severity": "INFO",
                        "title": f"{len(no_ais)} expected arrivals without AIS match",
                        "detail": "Name mismatch, AIS gap, or not yet in range",
                    }
                )

        if not matches.empty:
            in_port = matches[matches["status"].astype(str).str.contains("IN PORT", na=False)]
            if len(in_port) >= 1:
                alerts.append(
                    {
                        "severity": "INFO",
                        "title": f"{len(in_port)} KPA vessel(s) AIS-confirmed near/in port",
                        "detail": "Matched against live AIS box",
                    }
                )
        if not alerts:
            alerts.append(
                {
                    "severity": "INFO",
                    "title": "Ops board nominal",
                    "detail": "No elevated marine or arrival-pressure flags",
                }
            )
        return alerts

    def executive_brief(self, pack: PortOpsPack) -> str:
        k = pack.kpis
        parts = [
            f"**Mombasa Port Ops Board** · {pack.generated_at}",
            f"KPA list **{k.get('kpa_vessels', 0)}** vessels (report **{k.get('kpa_report_date') or '—'}**). "
            f"AIS near-port **{k.get('ais_near', 0)}** · matches **{k.get('matches', 0)}**.",
        ]
        if pack.marine:
            parts.append(
                f"Seas: wave **{pack.marine.get('wave_height_m') or '—'} m**, "
                f"swell **{pack.marine.get('swell_height_m') or '—'} m**, "
                f"SST **{pack.marine.get('sea_temp_c') or '—'} °C**."
            )
        if pack.weather:
            parts.append(
                f"Wx: **{pack.weather.get('temp_c') or '—'} °C**, "
                f"wind **{pack.weather.get('wind_ms') or '—'} m/s**."
            )
        if pack.alerts:
            top = pack.alerts[0]
            parts.append(f"Top flag: **{top.get('severity')}** — {top.get('title')}.")
        parts.append(
            "_Decision-support fusion of KPA public list + AIS + free marine weather. Not official KPA/IMO advice._"
        )
        return "\n\n".join(parts)

    def load_pack(
        self,
        ais_radius_nm: float = 40.0,
        ais_hours: int = 36,
        match_min: float = 0.55,
    ) -> PortOpsPack:
        self.errors = []
        now = _utcnow()
        kpa = self.load_kpa()
        ais = self.load_ais_near(radius_nm=ais_radius_nm, hours=ais_hours)
        matches, unmatched = self.match_kpa_ais(kpa, ais, min_score=match_min)
        weather, marine = self.load_weather_marine()
        port_hint = self.load_port_kpi_hint()
        board = self.build_arrival_board(kpa, matches)

        berth_load = pd.DataFrame()
        agent_mix = pd.DataFrame()
        cargo_mix = pd.DataFrame()
        if not kpa.empty:
            if "berth" in kpa.columns:
                berth_load = (
                    kpa.groupby(kpa["berth"].fillna("TBA").astype(str))
                    .size()
                    .reset_index(name="vessels")
                    .sort_values("vessels", ascending=False)
                )
            if "agent" in kpa.columns:
                agent_mix = (
                    kpa.groupby(kpa["agent"].fillna("Unknown").astype(str))
                    .size()
                    .reset_index(name="vessels")
                    .sort_values("vessels", ascending=False)
                    .head(15)
                )
            if "cargo" in kpa.columns:
                cargo_mix = (
                    kpa.groupby(kpa["cargo"].fillna("Unspecified").astype(str))
                    .size()
                    .reset_index(name="vessels")
                    .sort_values("vessels", ascending=False)
                    .head(15)
                )

        # arrivals next 48h
        next48 = 0
        if not board.empty and "hours_to_eta" in board.columns:
            h = pd.to_numeric(board["hours_to_eta"], errors="coerce")
            next48 = int(((h >= 0) & (h <= 48)).sum())

        kpis = {
            "kpa_vessels": int(kpa["vessel_name"].nunique()) if not kpa.empty and "vessel_name" in kpa.columns else len(kpa),
            "kpa_rows": len(kpa),
            "kpa_report_date": str(kpa["report_date"].iloc[0])[:10]
            if not kpa.empty and "report_date" in kpa.columns and pd.notna(kpa["report_date"].iloc[0])
            else None,
            "ais_near": len(ais),
            "matches": len(matches),
            "unmatched_kpa": len(unmatched),
            "arrivals_48h": next48,
            "wave_m": marine.get("wave_height_m"),
            "temp_c": weather.get("temp_c"),
            "wind_ms": weather.get("wind_ms"),
            "port_performance": port_hint.get("performance_score") or port_hint.get("performance"),
            "match_rate_pct": round(100.0 * len(matches) / max(1, len(kpa)), 1) if not kpa.empty else 0.0,
        }

        pack = PortOpsPack(
            generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
            kpis=kpis,
            kpa=kpa,
            ais_near=ais,
            matches=matches,
            unmatched_kpa=unmatched,
            weather=weather,
            marine=marine,
            arrival_board=board,
            berth_load=berth_load,
            agent_mix=agent_mix,
            cargo_mix=cargo_mix,
            errors=list(self.errors),
        )
        pack.alerts = self.build_alerts(kpa, matches, marine, weather, board)
        pack.brief = self.executive_brief(pack)
        return pack

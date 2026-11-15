"""
Home cockpit aggregator — multi-domain situation for OceanWatch Home.

Pulls AIS, port, fishing, alerts, events, ocean/env, and warehouse freshness
into one operator-facing pack so Home.py stays presentation-focused.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


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
    from db_utils import get_db_uri as _ing  # type: ignore

    return _ing()


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


@dataclass
class DomainCard:
    key: str
    title: str
    icon: str
    status: str  # GREEN | AMBER | RED | UNKNOWN | OFF
    score: float
    headline: str
    metrics: dict[str, Any] = field(default_factory=dict)
    page: str = ""
    detail: str = ""


@dataclass
class HomePack:
    generated_at: str
    overall: str
    overall_score: float
    overall_label: str
    kpis: dict[str, Any]
    domains: list[DomainCard]
    attention: list[dict[str, Any]]
    timeline: list[dict[str, Any]]
    freshness: pd.DataFrame
    recent_events: pd.DataFrame
    fishing_summary: dict[str, Any]
    port_summary: dict[str, Any]
    next_actions: list[dict[str, Any]]
    launchpad: list[dict[str, Any]]
    errors: list[str] = field(default_factory=list)


class HomeCockpitService:
    def __init__(self, engine: Optional[Engine] = None, db_uri: Optional[str] = None):
        if engine is not None:
            self.engine = engine
        else:
            self.engine = create_engine(
                _sa_uri(db_uri or _resolve_uri()),
                pool_pre_ping=True,
                pool_size=2,
                max_overflow=0,
                connect_args={"connect_timeout": 20},
            )
        self.errors: list[str] = []
        self._tables: dict[str, bool] = {}

    def qdf(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        try:
            with self.engine.connect() as conn:
                return pd.read_sql(text(sql), conn, params=params or {})
        except Exception as exc:  # noqa: BLE001
            self.errors.append(str(exc))
            logger.debug("home qdf fail: %s", exc)
            return pd.DataFrame()

    def scalar(self, sql: str, default: Any = 0, params: Optional[dict] = None) -> Any:
        df = self.qdf(sql, params)
        if df.empty:
            return default
        v = df.iloc[0, 0]
        return default if v is None else v

    def table_exists(self, name: str) -> bool:
        if name in self._tables:
            return self._tables[name]
        df = self.qdf(
            """
            SELECT 1 AS ok FROM information_schema.tables
            WHERE table_schema='public' AND table_name=:n LIMIT 1
            """,
            {"n": name},
        )
        ok = not df.empty
        self._tables[name] = ok
        return ok

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

    def _first_col(self, table: str, candidates: list[str]) -> str | None:
        cols = self.columns(table)
        for c in candidates:
            if c.lower() in cols:
                return c
        return None

    def _count_since(
        self,
        table: str,
        ts_candidates: list[str],
        hours: int,
        distinct_mmsi: bool = False,
    ) -> int:
        if not self.table_exists(table):
            return 0
        ts = self._first_col(table, ts_candidates)
        mmsi = self._first_col(table, ["mmsi"]) if distinct_mmsi else None
        if distinct_mmsi and mmsi and ts:
            sql = f"""
                SELECT COUNT(DISTINCT CAST({mmsi} AS TEXT)) FROM {table}
                WHERE {ts} > NOW() - INTERVAL '{int(hours)} hours'
            """
        elif distinct_mmsi and mmsi:
            sql = f"SELECT COUNT(DISTINCT CAST({mmsi} AS TEXT)) FROM {table}"
        elif ts:
            sql = f"""
                SELECT COUNT(*) FROM {table}
                WHERE {ts} > NOW() - INTERVAL '{int(hours)} hours'
            """
        else:
            sql = f"SELECT COUNT(*) FROM {table}"
        return int(self.scalar(sql, 0) or 0)

    def build(self, lookback_h: int = 24, persona: str = "Operator") -> HomePack:
        self.errors = []
        now = _utcnow()
        lb = max(6, min(int(lookback_h), 168))


        # Always defined so NameError cannot occur later in domains/attention/kpis
        ops_live: dict[str, Any] = {
            "kpa_vessels": 0,
            "kpa_report_date": None,
            "ais_matches": 0,
            "arrivals_48h": 0,
            "wave_m": None,
            "temp_c": None,
            "wind_ms": None,
            "match_rate_pct": 0.0,
        }
        # ---- core counts ----
        vessels = self._count_since(
            "fact_ais_positions",
            ["event_time", "ts", "timestamp", "msg_time", "position_time", "created_at"],
            lb,
            distinct_mmsi=True,
        )
        if vessels == 0:
            vessels = self._count_since(
                "fact_vessel_profiles",
                ["updated_at", "as_of", "created_at"],
                lb,
                distinct_mmsi=True,
            )
        if vessels == 0 and self.table_exists("vessels"):
            vessels = int(self.scalar("SELECT COUNT(DISTINCT mmsi) FROM vessels", 0) or 0)

        alerts = self._count_since(
            "fact_alerts",
            ["created_at", "detected_at", "ts", "event_time"],
            lb,
        )
        if alerts == 0:
            alerts = self._count_since(
                "fact_vessel_anomalies",
                ["detected_at", "created_at", "ts"],
                lb,
            )
        if alerts == 0 and self.table_exists("unified_risk"):
            cols = self.columns("unified_risk")
            level_c = next((c for c in ("risk_level", "severity", "level") if c in cols), None)
            if level_c:
                alerts = int(
                    self.scalar(
                        f"""
                        SELECT COUNT(*) FROM unified_risk
                        WHERE LOWER(COALESCE(CAST({level_c} AS TEXT), ''))
                              IN ('high','critical','severe')
                        """,
                        0,
                    )
                    or 0
                )

        high_risk = 0
        if self.table_exists("unified_risk"):
            cols = self.columns("unified_risk")
            level_c = next((c for c in ("risk_level", "severity", "level") if c in cols), None)
            if level_c:
                high_risk = int(
                    self.scalar(
                        f"""
                        SELECT COUNT(*) FROM unified_risk
                        WHERE LOWER(COALESCE(CAST({level_c} AS TEXT), ''))
                              IN ('high','critical','severe')
                        """,
                        0,
                    )
                    or 0
                )
        if high_risk == 0 and self.table_exists("fact_vessel_behaviour_scores"):
            cols = self.columns("fact_vessel_behaviour_scores")
            score_c = next((c for c in ("risk_score", "anomaly_score", "score") if c in cols), None)
            if score_c:
                high_risk = int(
                    self.scalar(
                        f"SELECT COUNT(*) FROM fact_vessel_behaviour_scores WHERE COALESCE({score_c}, 0) >= 70",
                        0,
                    )
                    or 0
                )

        # Port
        port_summary: dict[str, Any] = {
            "ops_risk": 0.0,
            "ops_level": "—",
            "congestion": 0.0,
            "performance": 0.0,
            "arrivals": 0,
            "departures": 0,
            "pressure": 0.0,
            "drivers": "",
        }
        try:
            from services.port_intelligence import PortIntelligenceService

            pi = PortIntelligenceService(engine=self.engine)
            b = pi.load_bundle(activity_limit=80)
            k = pi.kpis(b)
            port_summary.update(
                {
                    "ops_risk": k.get("ops_risk") or 0.0,
                    "ops_level": k.get("ops_level") or "—",
                    "congestion": k.get("congestion_index") or 0.0,
                    "performance": k.get("performance_score") or 0.0,
                    "arrivals": k.get("arrivals") or 0,
                    "departures": k.get("departures") or 0,
                    "pressure": k.get("pressure_index") or 0.0,
                    "drivers": k.get("drivers") or "",
                    "brief": pi.executive_brief(b) if b.has_any else "",
                    "alerts": pi.watchlist_alerts(b).to_dict("records") if b.has_any else [],
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"port: {exc}")
            if self.table_exists("fact_port_ops_risk"):
                row = self.qdf(
                    """
                    SELECT composite_ops_risk, risk_level, drivers
                    FROM fact_port_ops_risk
                    ORDER BY as_of DESC NULLS LAST LIMIT 1
                    """
                )
                if not row.empty:
                    port_summary["ops_risk"] = float(row.iloc[0].get("composite_ops_risk") or 0)
                    port_summary["ops_level"] = str(row.iloc[0].get("risk_level") or "—")
                    port_summary["drivers"] = str(row.iloc[0].get("drivers") or "")


        # KPA / live ops fusion
        try:
            from services.port_ops_board import PortOpsBoardService

            ops = PortOpsBoardService(engine=self.engine).load_pack(
                ais_radius_nm=40.0, ais_hours=min(int(lb), 48), match_min=0.55
            )
            ops_live.update(
                {
                    "kpa_vessels": ops.kpis.get("kpa_vessels") or 0,
                    "kpa_report_date": ops.kpis.get("kpa_report_date"),
                    "ais_matches": ops.kpis.get("matches") or 0,
                    "arrivals_48h": ops.kpis.get("arrivals_48h") or 0,
                    "wave_m": ops.kpis.get("wave_m"),
                    "temp_c": ops.kpis.get("temp_c"),
                    "wind_ms": ops.kpis.get("wind_ms"),
                    "match_rate_pct": ops.kpis.get("match_rate_pct") or 0.0,
                    "brief": (ops.brief or "")[:500],
                    "alerts": ops.alerts[:5],
                }
            )
            port_summary["kpa_vessels"] = ops_live["kpa_vessels"]
            port_summary["kpa_report_date"] = ops_live["kpa_report_date"]
            port_summary["arrivals_48h"] = ops_live["arrivals_48h"]
            port_summary["wave_m"] = ops_live["wave_m"]
            port_summary["ops_live"] = ops_live
            if ops_live.get("brief"):
                base_brief = str(port_summary.get("brief") or "").strip()
                port_summary["brief"] = (
                    (base_brief + "\n\n" if base_brief else "") + str(ops_live["brief"])
                )[:1200]
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"ops_board: {exc}")
            if self.table_exists("fact_kpa_shipping_movement"):
                ops_live["kpa_vessels"] = int(
                    self.scalar(
                        """
                        SELECT COUNT(DISTINCT vessel_name) FROM fact_kpa_shipping_movement
                        WHERE report_date = (SELECT MAX(report_date) FROM fact_kpa_shipping_movement)
                        """,
                        0,
                    )
                    or 0
                )
            if self.table_exists("fact_live_marine"):
                mrow = self.qdf(
                    """
                    SELECT wave_height_m FROM fact_live_marine
                    WHERE location='Mombasa' ORDER BY observed_at DESC NULLS LAST LIMIT 1
                    """
                )
                if not mrow.empty:
                    ops_live["wave_m"] = mrow.iloc[0].get("wave_height_m")
            port_summary["ops_live"] = ops_live

        # Fishing
        fishing: dict[str, Any] = {"events": 0, "hours": 0.0, "vessels": 0, "source": "—"}
        if self.table_exists("fact_gfw_fishing_effort"):
            fishing["source"] = "GFW"
            cols = self.columns("fact_gfw_fishing_effort")
            hours_c = next((c for c in ("fishing_hours", "hours", "effort_hours") if c in cols), None)
            day_c = next((c for c in ("date", "event_date", "day", "created_at") if c in cols), None)
            mmsi_c = "mmsi" if "mmsi" in cols else None
            days = max(lb // 24, 1)
            if hours_c and day_c:
                fishing["hours"] = float(
                    self.scalar(
                        f"""
                        SELECT COALESCE(SUM({hours_c}), 0) FROM fact_gfw_fishing_effort
                        WHERE {day_c}::timestamp >= CURRENT_DATE - INTERVAL '{days} days'
                        """,
                        0.0,
                    )
                    or 0.0
                )
            elif hours_c:
                fishing["hours"] = float(
                    self.scalar(
                        f"SELECT COALESCE(SUM({hours_c}), 0) FROM fact_gfw_fishing_effort",
                        0.0,
                    )
                    or 0.0
                )
            if mmsi_c and day_c:
                fishing["vessels"] = int(
                    self.scalar(
                        f"""
                        SELECT COUNT(DISTINCT CAST({mmsi_c} AS TEXT)) FROM fact_gfw_fishing_effort
                        WHERE {day_c}::timestamp >= CURRENT_DATE - INTERVAL '{days} days'
                        """,
                        0,
                    )
                    or 0
                )
        if float(fishing.get("hours") or 0) == 0 and self.table_exists("fact_fishing_activity"):
            fishing["source"] = fishing["source"] if fishing["source"] != "—" else "fishing_activity"
            fishing["events"] = self._count_since(
                "fact_fishing_activity", ["event_time", "ts", "created_at"], lb
            )
        if int(fishing.get("events") or 0) == 0 and self.table_exists("fact_fishing_events"):
            fishing["events"] = self._count_since(
                "fact_fishing_events", ["event_time", "ts", "created_at"], lb
            )

        # Ocean / bloom
        ocean_hint = "—"
        bloom_score = 0.0
        if self.table_exists("fact_bloom_risk"):
            cols = self.columns("fact_bloom_risk")
            score_c = next((c for c in ("risk_score", "score", "bloom_score") if c in cols), None)
            level_c = next((c for c in ("risk_level", "level", "status") if c in cols), None)
            region_c = next((c for c in ("region", "region_id", "area") if c in cols), None)
            order_c = next((c for c in ("as_of", "created_at", "metric_date") if c in cols), None)
            select_bits = [c for c in (score_c, level_c, region_c, order_c) if c]
            if select_bits:
                order_sql = f"ORDER BY {order_c} DESC NULLS LAST" if order_c else ""
                br = self.qdf(
                    f"SELECT {', '.join(select_bits)} FROM fact_bloom_risk {order_sql} LIMIT 1"
                )
                if not br.empty:
                    if score_c:
                        bloom_score = float(br.iloc[0].get(score_c) or 0)
                    lvl = br.iloc[0].get(level_c) if level_c else None
                    ocean_hint = f"Bloom {lvl or f'{bloom_score:.0f}'}"
        if ocean_hint == "—" and self.table_exists("fact_ocean_conditions"):
            cols = self.columns("fact_ocean_conditions")
            sst_c = next((c for c in ("sst", "sea_surface_temp", "temperature", "temp_c") if c in cols), None)
            chl_c = next((c for c in ("chlorophyll", "chl", "chl_a", "chlor_a") if c in cols), None)
            asof_c = next((c for c in ("as_of", "created_at", "obs_time", "date") if c in cols), None)
            bits = [c for c in (sst_c, chl_c, asof_c) if c]
            if bits:
                order_sql = f"ORDER BY {asof_c} DESC NULLS LAST" if asof_c else ""
                oc = self.qdf(
                    f"SELECT {', '.join(bits)} FROM fact_ocean_conditions {order_sql} LIMIT 1"
                )
                if not oc.empty:
                    sst = oc.iloc[0].get(sst_c) if sst_c else None
                    chl = oc.iloc[0].get(chl_c) if chl_c else None
                    if sst is not None or chl is not None:
                        ocean_hint = f"SST {sst} · chl {chl}"
                    else:
                        ocean_hint = "Ocean conditions"

        # Events
        events_n = 0
        recent_events = pd.DataFrame()
        for tbl, ts_candidates in (
            ("fact_maritime_events", ["event_time", "created_at", "ts"]),
            ("fact_geofence_events", ["event_time", "created_at", "ts"]),
            ("fact_port_activity", ["event_time", "created_at"]),
        ):
            if not self.table_exists(tbl):
                continue
            n = self._count_since(tbl, list(ts_candidates), lb)
            events_n += n
            if recent_events.empty:
                order = self._first_col(tbl, list(ts_candidates))
                if order:
                    recent_events = self.qdf(
                        f"""
                        SELECT * FROM {tbl}
                        ORDER BY {order} DESC NULLS LAST
                        LIMIT 25
                        """
                    )
                    if not recent_events.empty:
                        recent_events = recent_events.copy()
                        recent_events["_source_table"] = tbl

        # Freshness mosaic
        fresh_rows = []
        catalog = [
            ("fact_ais_positions", ["event_time", "ts", "timestamp", "created_at"], "AIS positions"),
            ("fact_vessel_profiles", ["updated_at", "as_of", "created_at"], "Vessel profiles"),
            ("fact_port_performance", ["metric_date", "created_at"], "Port performance"),
            ("fact_port_ops_risk", ["as_of", "created_at"], "Port ops risk"),
            ("fact_port_activity", ["event_time", "created_at"], "Port activity"),
            ("fact_alerts", ["created_at", "detected_at", "ts"], "Alerts"),
            ("fact_vessel_anomalies", ["detected_at", "created_at"], "Anomalies"),
            ("fact_gfw_fishing_effort", ["date", "event_date", "day", "created_at"], "GFW fishing"),
            ("fact_fishing_activity", ["event_time", "ts", "created_at"], "Fishing activity"),
            ("fact_bloom_risk", ["as_of", "created_at"], "Bloom risk"),
            ("fact_maritime_events", ["event_time", "created_at"], "Maritime events"),
            ("fact_geofence_events", ["event_time", "created_at"], "Geofence events"),
        ]
        ok_n = 0
        total_n = 0
        for table, ts_candidates, layer_label in catalog:
            total_n += 1
            if not self.table_exists(table):
                fresh_rows.append(
                    {
                        "layer": layer_label,
                        "table": table,
                        "status": "MISSING",
                        "rows": 0,
                        "latest": None,
                        "age_hours": None,
                    }
                )
                continue
            cnt = int(self.scalar(f"SELECT COUNT(*) FROM {table}", 0) or 0)
            latest = None
            age_h = None
            for c in ts_candidates:
                # probe column
                col_ok = self.qdf(
                    """
                    SELECT 1 AS ok FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=:t AND column_name=:c
                    LIMIT 1
                    """,
                    {"t": table, "c": c},
                )
                if col_ok.empty:
                    continue
                df = self.qdf(f"SELECT MAX({c}) AS mx FROM {table}")
                if not df.empty and df.iloc[0]["mx"] is not None:
                    latest = df.iloc[0]["mx"]
                    try:
                        ts = pd.to_datetime(latest, utc=True, errors="coerce")
                        if pd.notna(ts):
                            age_h = (now - ts.to_pydatetime()).total_seconds() / 3600.0
                    except Exception:  # noqa: BLE001
                        age_h = None
                    break
            status = "OK"
            if cnt == 0:
                status = "EMPTY"
            elif age_h is not None and age_h > 72:
                status = "STALE"
            elif age_h is not None and age_h > 36:
                status = "AGING"
            else:
                ok_n += 1
            fresh_rows.append(
                {
                    "layer": layer_label,
                    "table": table,
                    "status": status,
                    "rows": cnt,
                    "latest": str(latest) if latest is not None else None,
                    "age_hours": round(age_h, 1) if age_h is not None else None,
                }
            )
        freshness = pd.DataFrame(fresh_rows)

        # Domains
        def status_from_score(score: float, invert: bool = True) -> str:
            # higher score = more risk when invert
            s = float(score)
            if invert:
                if s >= 70:
                    return "RED"
                if s >= 45:
                    return "AMBER"
                return "GREEN"
            if s >= 70:
                return "GREEN"
            if s >= 40:
                return "AMBER"
            return "RED"

        domains: list[DomainCard] = []

        ais_status = "GREEN" if vessels > 0 else "AMBER"
        domains.append(
            DomainCard(
                key="ais",
                title="AIS & tracking",
                icon="radar",
                status=ais_status if vessels else "AMBER",
                score=min(100.0, vessels / 5.0),
                headline=f"{vessels} vessels in lookback",
                metrics={"vessels": vessels, "lookback_h": lb},
                page="pages/4_Vessel_Tracking.py",
                detail="Historical tracks · port calls · behaviour",
            )
        )

        port_score = float(port_summary.get("ops_risk") or 0)
        domains.append(
            DomainCard(
                key="port",
                title="Port — Mombasa",
                icon="anchor",
                status=status_from_score(port_score),
                score=port_score,
                headline=f"Ops {port_summary.get('ops_level')} · cong {float(port_summary.get('congestion') or 0):.0f}",
                metrics=port_summary,
                page="pages/8_Port_Intelligence.py",
                detail=str(port_summary.get("drivers") or "Performance · berth · forecasts"),
            )
        )

        fish_pressure = float(fishing.get("hours") or 0) + float(fishing.get("events") or 0) * 2
        domains.append(
            DomainCard(
                key="fishing",
                title="Fisheries",
                icon="phishing",
                status="AMBER" if fish_pressure > 50 else "GREEN" if fish_pressure > 0 else "UNKNOWN",
                score=min(100.0, fish_pressure),
                headline=(
                    f"{fishing.get('hours', 0):.0f}h effort · {fishing.get('events', 0)} events"
                    if fishing.get("source") != "—"
                    else "No fishing layer loaded"
                ),
                metrics=fishing,
                page="pages/30_Fisheries_Intelligence.py",
                detail=f"Source: {fishing.get('source')}",
            )
        )

        alert_status = "RED" if alerts >= 15 or high_risk >= 10 else "AMBER" if alerts >= 5 or high_risk >= 3 else "GREEN"
        
        # Port ops board domain (KPA + AIS + seas)
        wave_v = ops_live.get("wave_m")
        try:
            wave_f = float(wave_v) if wave_v is not None else None
        except (TypeError, ValueError):
            wave_f = None
        ops_status = "GREEN"
        ops_score = 78.0
        if (ops_live.get("kpa_vessels") or 0) == 0:
            ops_status, ops_score = "AMBER", 55.0
        if (ops_live.get("arrivals_48h") or 0) >= 8:
            ops_status, ops_score = "AMBER", 50.0
        if wave_f is not None and wave_f >= 2.5:
            ops_status, ops_score = "RED", 35.0
        elif wave_f is not None and wave_f >= 1.8:
            ops_status = "AMBER" if ops_status == "GREEN" else ops_status
            ops_score = min(ops_score, 58.0)
        domains.append(
            DomainCard(
                key="ops_board",
                title="Port Ops Board",
                icon="anchor",
                status=ops_status,
                score=ops_score,
                headline=(
                    f"KPA {ops_live.get('kpa_vessels') or 0} · "
                    f"match {ops_live.get('ais_matches') or 0} · "
                    f"ETA48h {ops_live.get('arrivals_48h') or 0}"
                ),
                metrics={
                    "kpa": ops_live.get("kpa_vessels") or 0,
                    "matches": ops_live.get("ais_matches") or 0,
                    "wave_m": wave_f,
                },
                detail="KPA 14-day · AIS match · Open-Meteo seas",
                page="pages/40_Port_Ops_Board.py",
            )
        )

        domains.append(
            DomainCard(
                key="risk",
                title="Risk & anomalies",
                icon="warning",
                status=alert_status,
                score=min(100.0, alerts * 4.0 + high_risk * 5.0),
                headline=f"{alerts} alerts · {high_risk} high-risk entities",
                metrics={"alerts": alerts, "high_risk": high_risk},
                page="pages/7_Operational_Alerts.py",
                detail="Anomaly engine · subscriptions · notifications",
            )
        )

        domains.append(
            DomainCard(
                key="events",
                title="Maritime events",
                icon="sensors",
                status="AMBER" if events_n > 40 else "GREEN" if events_n > 0 else "UNKNOWN",
                score=min(100.0, events_n * 1.5),
                headline=f"{events_n} events in lookback",
                metrics={"events": events_n},
                page="pages/34_Maritime_Events.py",
                detail="Geofence · port activity · fused events",
            )
        )

        env_status = status_from_score(bloom_score) if bloom_score else ("GREEN" if ocean_hint != "—" else "UNKNOWN")
        domains.append(
            DomainCard(
                key="ocean",
                title="Ocean & habitat",
                icon="water",
                status=env_status,
                score=bloom_score or (30.0 if ocean_hint != "—" else 0.0),
                headline=ocean_hint if ocean_hint != "—" else "No ocean layer",
                metrics={"bloom_score": bloom_score, "hint": ocean_hint},
                page="pages/13_Bloom_Risk.py",
                detail="Bloom risk · habitat suitability · research data",
            )
        )

        data_health = (ok_n / total_n * 100.0) if total_n else 0.0
        domains.append(
            DomainCard(
                key="data",
                title="Data platform",
                icon="database",
                status="GREEN" if data_health >= 70 else "AMBER" if data_health >= 40 else "RED",
                score=data_health,
                headline=f"{ok_n}/{total_n} layers healthy",
                metrics={"ok": ok_n, "total": total_n, "pct": round(data_health, 1)},
                page="pages/32_Data_Catalog.py",
                detail="Catalog · quality · platform ops",
            )
        )

        domains.append(
            DomainCard(
                key="intel",
                title="Intelligence products",
                icon="description",
                status="GREEN",
                score=75.0,
                headline="Reports · map · WIO briefings",
                metrics={},
                page="pages/6_Intelligence_Reports.py",
                detail="Executive summary · regional coverage · API",
            )
        )

        # Overall posture
        risk_load = 0.0
        risk_load += min(35.0, port_score * 0.35)
        risk_load += min(25.0, alerts * 2.5)
        risk_load += min(20.0, high_risk * 3.0)
        risk_load += min(10.0, (100 - data_health) * 0.15)
        risk_load += min(10.0, bloom_score * 0.1)
        overall_score = max(0.0, min(100.0, 100.0 - risk_load))
        if overall_score >= 75:
            overall, overall_label = "GREEN", "Stable watch"
        elif overall_score >= 50:
            overall, overall_label = "AMBER", "Elevated attention"
        else:
            overall, overall_label = "RED", "Priority response"

        # Attention queue
        attention: list[dict[str, Any]] = []
        if port_score >= 45:
            attention.append(
                {
                    "severity": "HIGH" if port_score >= 70 else "WATCH",
                    "domain": "Port",
                    "title": f"Mombasa ops risk {port_summary.get('ops_level')}",
                    "detail": port_summary.get("drivers") or f"Congestion {port_summary.get('congestion')}",
                    "page": "pages/8_Port_Intelligence.py",
                }
            )
        if alerts >= 5:
            attention.append(
                {
                    "severity": "HIGH" if alerts >= 15 else "WATCH",
                    "domain": "Alerts",
                    "title": f"{alerts} alerts in last {lb}h",
                    "detail": f"{high_risk} high-risk entities on board",
                    "page": "pages/7_Operational_Alerts.py",
                }
            )
        if high_risk >= 5:
            attention.append(
                {
                    "severity": "HIGH",
                    "domain": "Risk",
                    "title": f"{high_risk} high-risk vessels/entities",
                    "detail": "Open vessel intelligence and anomaly engine",
                    "page": "pages/5_Vessel_Intelligence.py",
                }
            )
        stale = freshness[freshness["status"].isin(["STALE", "MISSING", "EMPTY"])] if not freshness.empty else pd.DataFrame()
        if not stale.empty:
            attention.append(
                {
                    "severity": "WATCH",
                    "domain": "Data",
                    "title": f"{len(stale)} data layers need attention",
                    "detail": ", ".join(stale["layer"].head(4).tolist()),
                    "page": "pages/32_Data_Catalog.py",
                }
            )
        if fish_pressure > 80:
            attention.append(
                {
                    "severity": "WATCH",
                    "domain": "Fisheries",
                    "title": "Elevated fishing effort signal",
                    "detail": f"{fishing.get('hours', 0):.0f}h / {fishing.get('events', 0)} events",
                    "page": "pages/15_GFW_Fishing_Effort.py",
                }
            )
        if bloom_score >= 55:
            attention.append(
                {
                    "severity": "WATCH",
                    "domain": "Ocean",
                    "title": f"Bloom risk elevated ({bloom_score:.0f})",
                    "detail": ocean_hint,
                    "page": "pages/13_Bloom_Risk.py",
                }
            )
        if not attention:
            attention.append(
                {
                    "severity": "INFO",
                    "domain": "Watch",
                    "title": "No priority breaches",
                    "detail": "Continue routine EEZ / port monitoring",
                    "page": "pages/0_Kenya_EEZ_Today.py",
                }
            )

        # Timeline (synthetic from available facts)
        timeline: list[dict[str, Any]] = []
        timeline.append(
            {
                "when": now.strftime("%H:%M UTC"),
                "kind": "pulse",
                "text": f"Home pulse {overall} ({overall_score:.0f}) · {vessels} AIS · {alerts} alerts",
            }
        )
        if port_summary.get("ops_level") and port_summary.get("ops_level") != "—":
            timeline.append(
                {
                    "when": "port",
                    "kind": "port",
                    "text": f"Mombasa ops {port_summary.get('ops_level')} · perf {float(port_summary.get('performance') or 0):.0f} · "
                    f"{port_summary.get('arrivals')}/{port_summary.get('departures')} arr/dep",
                }
            )
        if not recent_events.empty:
            for _, r in recent_events.head(8).iterrows():
                et = r.get("event_time") or r.get("created_at") or r.get("ts") or ""
                label = r.get("event_type") or r.get("event_name") or r.get("title") or "event"
                vessel = r.get("vessel_name") or r.get("mmsi") or ""
                timeline.append(
                    {
                        "when": str(et)[:16],
                        "kind": str(r.get("_source_table") or "event"),
                        "text": f"{label} · {vessel}".strip(" ·"),
                    }
                )


        if (ops_live.get("kpa_vessels") or 0) == 0:
            attention.append(
                {
                    "severity": "INFO",
                    "domain": "Port Ops",
                    "title": "KPA 14-day list not loaded",
                    "detail": "Upload DOCX from kpa.co.ke/ShippingMovement",
                    "page": "pages/39_Live_Feeds_and_KPA.py",
                }
            )
        if (ops_live.get("arrivals_48h") or 0) >= 8:
            attention.append(
                {
                    "severity": "WATCH",
                    "domain": "Port Ops",
                    "title": f"{ops_live.get('arrivals_48h')} KPA arrivals within 48h",
                    "detail": "Berth pressure — open Port Ops Board",
                    "page": "pages/40_Port_Ops_Board.py",
                }
            )
        try:
            _wv = float(ops_live["wave_m"]) if ops_live.get("wave_m") is not None else None
        except (TypeError, ValueError):
            _wv = None
        if _wv is not None and _wv >= 2.5:
            attention.append(
                {
                    "severity": "HIGH",
                    "domain": "Marine",
                    "title": f"Elevated seas at Mombasa ({_wv:.1f} m)",
                    "detail": "Open-Meteo marine — pilotage caution",
                    "page": "pages/40_Port_Ops_Board.py",
                }
            )

        # Next actions (persona-aware)
        next_actions = self._next_actions(persona, overall, domains, attention)

        # Launchpad
        launchpad = self._launchpad(persona)

        kpis = {
            "vessels": vessels,
            "alerts": alerts,
            "high_risk": high_risk,
            "port_ops": port_score,
            "port_level": port_summary.get("ops_level"),
            "port_cong": port_summary.get("congestion"),
            "fishing_hours": fishing.get("hours") or 0,
            "fishing_events": fishing.get("events") or 0,
            "events": events_n,
            "data_health_pct": round(data_health, 1),
            "lookback_h": lb,
            "ocean": ocean_hint,
            "kpa_vessels": ops_live.get("kpa_vessels") or 0,
            "kpa_report_date": ops_live.get("kpa_report_date"),
            "arrivals_48h": ops_live.get("arrivals_48h") or 0,
            "kpa_ais_matches": ops_live.get("ais_matches") or 0,
            "wave_m": ops_live.get("wave_m"),
            "temp_c": ops_live.get("temp_c"),
            "wind_ms": ops_live.get("wind_ms"),
        }

        return HomePack(
            generated_at=now.isoformat(timespec="seconds"),
            overall=overall,
            overall_score=round(overall_score, 1),
            overall_label=overall_label,
            kpis=kpis,
            domains=domains,
            attention=attention,
            timeline=timeline,
            freshness=freshness,
            recent_events=recent_events.head(40) if not recent_events.empty else recent_events,
            fishing_summary=fishing,
            port_summary=port_summary,
            next_actions=next_actions,
            launchpad=launchpad,
            errors=list(self.errors),
        )

    def _next_actions(
        self,
        persona: str,
        overall: str,
        domains: list[DomainCard],
        attention: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        # From attention first
        for a in attention[:4]:
            if a.get("severity") in ("HIGH", "CRITICAL", "WATCH"):
                actions.append(
                    {
                        "priority": a.get("severity"),
                        "title": a.get("title"),
                        "why": a.get("detail"),
                        "page": a.get("page"),
                        "domain": a.get("domain"),
                    }
                )
        p = (persona or "Operator").lower()
        extras = []
        if "exec" in p or "brief" in p:
            extras = [
                ("Executive Summary", "pages/1_Executive_Summary.py", "Board-ready posture"),
                ("Intelligence Reports", "pages/6_Intelligence_Reports.py", "Narrative products"),
                ("Regional Coverage", "pages/33_Regional_Coverage.py", "WIO footprint"),
            ]
        elif "fish" in p or "mcs" in p:
            extras = [
                ("Fisheries Intelligence", "pages/30_Fisheries_Intelligence.py", "MCS picture"),
                ("GFW Fishing Effort", "pages/15_GFW_Fishing_Effort.py", "Effort heat"),
                ("Anomaly Engine", "pages/23_Anomaly_Engine.py", "Dark activity"),
            ]
        elif "port" in p:
            extras = [
                ("Port Intelligence — Mombasa", "pages/8_Port_Intelligence.py", "Congestion & berth"),
                ("Port Risk", "pages/12_Port_Risk.py", "ML port risk"),
                ("Vessel Tracking", "pages/4_Vessel_Tracking.py", "Arrivals context"),
            ]
        elif "research" in p or "science" in p:
            extras = [
                ("Bloom Risk", "pages/13_Bloom_Risk.py", "Env signal"),
                ("Habitat Suitability", "pages/14_Habitat_Suitability.py", "Habitat layers"),
                ("Research Data", "pages/16_Research_Data.py", "Science packs"),
            ]
        else:
            extras = [
                ("Kenya EEZ Today", "pages/0_Kenya_EEZ_Today.py", "Daily EEZ watch"),
                ("Command Center", "pages/3_Command_Center.py", "Fused ops"),
                ("AIS Live", "pages/11_AIS_Live.py", "Near real-time plot"),
                ("Vessel Tracking", "pages/4_Vessel_Tracking.py", "Tracks & analytics"),
            ]
        have = {a.get("page") for a in actions}
        for title, page, why in extras:
            if page in have:
                continue
            actions.append(
                {
                    "priority": "INFO",
                    "title": title,
                    "why": why,
                    "page": page,
                    "domain": "Launch",
                }
            )
            if len(actions) >= 8:
                break
        if overall == "RED":
            actions.insert(
                0,
                {
                    "priority": "CRITICAL",
                    "title": "Open Command Center",
                    "why": "Overall posture is RED — fuse domains before tasking",
                    "page": "pages/3_Command_Center.py",
                    "domain": "Command",
                },
            )
        return actions[:8]

    def _launchpad(self, persona: str) -> list[dict[str, Any]]:
        base = [
            {"group": "Command", "title": "Kenya EEZ Today", "page": "pages/0_Kenya_EEZ_Today.py", "blurb": "Daily national watch"},
            {"group": "Command", "title": "Command Center", "page": "pages/3_Command_Center.py", "blurb": "Fused multi-domain ops"},
            {"group": "Command", "title": "Executive Summary", "page": "pages/1_Executive_Summary.py", "blurb": "Leadership brief"},
            {"group": "Command", "title": "Intelligence Map", "page": "pages/2_Intelligence_Map.py", "blurb": "Spatial picture"},
            {"group": "Maritime", "title": "AIS Live", "page": "pages/11_AIS_Live.py", "blurb": "Live positions"},
            {"group": "Maritime", "title": "Vessel Tracking", "page": "pages/4_Vessel_Tracking.py", "blurb": "Tracks & port calls"},
            {"group": "Maritime", "title": "Vessel Intelligence", "page": "pages/5_Vessel_Intelligence.py", "blurb": "Risk profiles"},
            {"group": "Maritime", "title": "Maritime Events", "page": "pages/34_Maritime_Events.py", "blurb": "Event bus feed"},
            {"group": "Port", "title": "Port Intelligence", "page": "pages/8_Port_Intelligence.py", "blurb": "Mombasa command"},
            {"group": "Port", "title": "Port Advanced", "page": "pages/29_Port_Intelligence_Advanced.py", "blurb": "Diagnostics"},
            {"group": "Port", "title": "Port Risk", "page": "pages/12_Port_Risk.py", "blurb": "ML risk"},
            {"group": "Fisheries", "title": "Fishing Activity", "page": "pages/9_Fishing_Activity.py", "blurb": "Activity layer"},
            {"group": "Fisheries", "title": "GFW Effort", "page": "pages/15_GFW_Fishing_Effort.py", "blurb": "Global Fishing Watch"},
            {"group": "Fisheries", "title": "Fisheries Intel", "page": "pages/30_Fisheries_Intelligence.py", "blurb": "MCS pack"},
            {"group": "Risk", "title": "Operational Alerts", "page": "pages/7_Operational_Alerts.py", "blurb": "Live alerts"},
            {"group": "Risk", "title": "Anomaly Engine", "page": "pages/23_Anomaly_Engine.py", "blurb": "Behavioural anomalies"},
            {"group": "Risk", "title": "Notifications", "page": "pages/38_Notifications.py", "blurb": "Delivery center"},
            {"group": "Ocean", "title": "Bloom Risk", "page": "pages/13_Bloom_Risk.py", "blurb": "HABs signal"},
            {"group": "Ocean", "title": "Habitat", "page": "pages/14_Habitat_Suitability.py", "blurb": "Suitability"},
            {"group": "Ocean", "title": "Research Data", "page": "pages/16_Research_Data.py", "blurb": "Science exports"},
            {"group": "Platform", "title": "Data Catalog", "page": "pages/32_Data_Catalog.py", "blurb": "Warehouse map"},
            {"group": "Platform", "title": "Platform Ops", "page": "pages/31_Platform_Operations.py", "blurb": "Jobs & health"},
            {"group": "Platform", "title": "Quality", "page": "pages/25_Quality_and_Provenance.py", "blurb": "Trust & lineage"},
            {"group": "Platform", "title": "API Access", "page": "pages/22_API_Access.py", "blurb": "Integration"},
        ]
        p = (persona or "").lower()
        if "port" in p:
            order = ["Port", "Maritime", "Command", "Risk", "Fisheries", "Ocean", "Platform"]
        elif "fish" in p or "mcs" in p:
            order = ["Fisheries", "Risk", "Maritime", "Command", "Port", "Ocean", "Platform"]
        elif "exec" in p:
            order = ["Command", "Risk", "Port", "Fisheries", "Ocean", "Maritime", "Platform"]
        elif "research" in p or "science" in p:
            order = ["Ocean", "Platform", "Fisheries", "Maritime", "Command", "Port", "Risk"]
        else:
            order = ["Command", "Maritime", "Port", "Risk", "Fisheries", "Ocean", "Platform"]
        rank = {g: i for i, g in enumerate(order)}
        return sorted(base, key=lambda x: (rank.get(x["group"], 99), x["title"]))

    def markdown_brief(self, pack: HomePack, ctx: Optional[dict[str, Any]] = None) -> str:
        ctx = ctx or {}
        lines = [
            f"# OceanWatch Home Brief",
            f"_Generated {pack.generated_at}_",
            "",
            f"**Posture:** {pack.overall} ({pack.overall_score}) — {pack.overall_label}",
            f"**Mission:** {ctx.get('region', 'Kenya EEZ')} · lookback {pack.kpis.get('lookback_h')}h · "
            f"persona {ctx.get('persona', 'Operator')}",
            "",
            "## KPIs",
            f"- Vessels: **{pack.kpis.get('vessels')}**",
            f"- Alerts: **{pack.kpis.get('alerts')}** · high-risk **{pack.kpis.get('high_risk')}**",
            f"- Port ops: **{pack.kpis.get('port_ops')}** ({pack.kpis.get('port_level')}) · "
            f"congestion **{float(pack.kpis.get('port_cong') or 0):.0f}**",
            f"- Fishing: **{pack.kpis.get('fishing_hours')}** h · events **{pack.kpis.get('fishing_events')}**",
            f"- Events: **{pack.kpis.get('events')}** · data health **{pack.kpis.get('data_health_pct')}%**",
            f"- Ocean: {pack.kpis.get('ocean')}",
            "",
            "## Attention",
        ]
        for a in pack.attention:
            lines.append(f"- **{a.get('severity')}** [{a.get('domain')}] {a.get('title')} — {a.get('detail')}")
        lines += ["", "## Domains"]
        for d in pack.domains:
            lines.append(f"- **{d.title}** `{d.status}` ({d.score:.0f}) — {d.headline}")
        if pack.port_summary.get("brief"):
            lines += ["", "## Port brief", pack.port_summary["brief"]]
        lines += ["", "## Next actions"]
        for a in pack.next_actions:
            lines.append(f"- **{a.get('priority')}** {a.get('title')} — {a.get('why')}")
        lines += [
            "",
            "---",
            "_OceanWatch decision-support only — not official KPA / KMA / Navy figures._",
        ]
        return "\n".join(lines)

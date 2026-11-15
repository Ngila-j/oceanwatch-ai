"""
Port Intelligence service — Mombasa (Phase 14 + AIS near-port).

Loads warehouse port tables, derives KPIs, trends, alerts, vessel mix,
what-if scenarios, and near-port AIS context for Streamlit pages.
"""

from __future__ import annotations

import logging
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

PORT = "Mombasa"
# Approximate Mombasa port / outer anchorage box (WGS84)
MOM_LAT, MOM_LON = -4.06, 39.65
MOM_RADIUS_NM = 18.0  # ~ near-port watch radius


def _resolve_uri() -> str:
    try:
        from db_config import get_db_uri

        return get_db_uri()
    except Exception:  # noqa: BLE001
        pass
    try:
        app = Path(__file__).resolve().parents[1]
        if str(app) not in sys.path:
            sys.path.insert(0, str(app))
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


def _num(row: Any, *keys: str, default: float = 0.0) -> float:
    if row is None:
        return default
    getter = row.get if hasattr(row, "get") else None
    for k in keys:
        try:
            v = getter(k) if getter else row[k]  # type: ignore[index]
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                return float(v)
        except Exception:  # noqa: BLE001
            continue
    return default


@dataclass
class PortBundle:
    performance: pd.DataFrame = field(default_factory=pd.DataFrame)
    congestion_fc: pd.DataFrame = field(default_factory=pd.DataFrame)
    arrival_fc: pd.DataFrame = field(default_factory=pd.DataFrame)
    berth: pd.DataFrame = field(default_factory=pd.DataFrame)
    ops_risk: pd.DataFrame = field(default_factory=pd.DataFrame)
    metrics: pd.DataFrame = field(default_factory=pd.DataFrame)
    activity: pd.DataFrame = field(default_factory=pd.DataFrame)
    errors: list[str] = field(default_factory=list)

    @property
    def has_phase14(self) -> bool:
        return not (
            self.performance.empty
            and self.congestion_fc.empty
            and self.arrival_fc.empty
            and self.berth.empty
            and self.ops_risk.empty
        )

    @property
    def has_any(self) -> bool:
        return self.has_phase14 or not self.metrics.empty or not self.activity.empty


class PortIntelligenceService:
    """Query + analytics for Mombasa Port Intelligence pages."""

    def __init__(self, engine: Optional[Engine] = None, db_uri: Optional[str] = None):
        if engine is not None:
            self.engine = engine
        else:
            uri = db_uri or _resolve_uri()
            self.engine = create_engine(
                _sa_uri(uri),
                pool_pre_ping=True,
                pool_size=2,
                max_overflow=0,
                connect_args={"connect_timeout": 25},
            )
        self._table_cache: dict[str, bool] = {}
        self.errors: list[str] = []

    def qdf(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        try:
            with self.engine.connect() as conn:
                return pd.read_sql(text(sql), conn, params=params or {})
        except Exception as exc:  # noqa: BLE001
            msg = f"{exc}"
            self.errors.append(msg)
            logger.debug("port_intel query failed: %s | %s", exc, sql[:120])
            return pd.DataFrame()

    def table_exists(self, name: str) -> bool:
        if name in self._table_cache:
            return self._table_cache[name]
        df = self.qdf(
            """
            SELECT 1 AS ok FROM information_schema.tables
            WHERE table_schema='public' AND table_name=:n LIMIT 1
            """,
            {"n": name},
        )
        ok = not df.empty
        self._table_cache[name] = ok
        return ok

    def load_bundle(self, activity_limit: int = 300) -> PortBundle:
        self.errors = []
        b = PortBundle()
        if self.table_exists("fact_port_performance"):
            b.performance = self.qdf("SELECT * FROM fact_port_performance ORDER BY metric_date")
        if self.table_exists("fact_port_congestion_forecast"):
            b.congestion_fc = self.qdf(
                "SELECT * FROM fact_port_congestion_forecast ORDER BY horizon_day"
            )
        if self.table_exists("fact_port_arrival_forecast"):
            b.arrival_fc = self.qdf(
                "SELECT * FROM fact_port_arrival_forecast ORDER BY horizon_day"
            )
        if self.table_exists("fact_berth_pressure"):
            b.berth = self.qdf(
                "SELECT * FROM fact_berth_pressure ORDER BY as_of DESC NULLS LAST LIMIT 10"
            )
        if self.table_exists("fact_port_ops_risk"):
            b.ops_risk = self.qdf(
                "SELECT * FROM fact_port_ops_risk ORDER BY as_of DESC NULLS LAST LIMIT 10"
            )
        if self.table_exists("fact_port_metrics"):
            b.metrics = self.qdf("SELECT * FROM fact_port_metrics ORDER BY metric_date")
        if self.table_exists("fact_port_activity"):
            b.activity = self.qdf(
                """
                SELECT * FROM fact_port_activity
                ORDER BY event_time DESC NULLS LAST
                LIMIT :lim
                """,
                {"lim": int(activity_limit)},
            )
            b.activity = self._normalize_activity(b.activity)
        b.errors = list(self.errors)
        return b

    @staticmethod
    def _normalize_activity(df: pd.DataFrame) -> pd.DataFrame:
        """Align seed column aliases used across phases."""
        if df.empty:
            return df
        out = df.copy()
        if "waiting_hours" not in out.columns and "dwell_hours" in out.columns:
            out["waiting_hours"] = pd.to_numeric(out["dwell_hours"], errors="coerce")
        elif "waiting_hours" in out.columns:
            out["waiting_hours"] = pd.to_numeric(out["waiting_hours"], errors="coerce")
            if "dwell_hours" in out.columns:
                out["waiting_hours"] = out["waiting_hours"].fillna(
                    pd.to_numeric(out["dwell_hours"], errors="coerce")
                )
        if "event_type" in out.columns:
            out["event_type"] = out["event_type"].astype(str).str.strip().str.upper()
        return out

    # ---- derived analytics -------------------------------------------------

    def series_frame(self, b: PortBundle) -> pd.DataFrame:
        """Prefer scored performance; fall back to base metrics."""
        src = b.performance if not b.performance.empty else b.metrics
        if src.empty:
            return src
        df = src.copy()
        df["metric_date"] = pd.to_datetime(df["metric_date"], errors="coerce")
        df = df.dropna(subset=["metric_date"]).sort_values("metric_date")
        # normalize aliases
        ren = {}
        if "arrival_count" in df.columns and "arrivals" not in df.columns:
            ren["arrival_count"] = "arrivals"
        if "departure_count" in df.columns and "departures" not in df.columns:
            ren["departure_count"] = "departures"
        if "vessel_count" in df.columns and "active_vessels" not in df.columns:
            ren["vessel_count"] = "active_vessels"
        if ren:
            df = df.rename(columns=ren)
        for c in (
            "arrivals",
            "departures",
            "active_vessels",
            "congestion_index",
            "avg_waiting_hours",
            "performance_score",
            "throughput_proxy",
            "balance_ratio",
            "container_vessels",
            "tankers",
            "fishing_vessels",
        ):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        if "throughput_proxy" not in df.columns and "arrivals" in df.columns:
            dep = df["departures"] if "departures" in df.columns else 0
            df["throughput_proxy"] = df["arrivals"].fillna(0) + pd.Series(dep).fillna(0)
        # rolling windows
        if "congestion_index" in df.columns:
            df["cong_ma7"] = df["congestion_index"].rolling(7, min_periods=1).mean()
        if "arrivals" in df.columns:
            df["arr_ma7"] = df["arrivals"].rolling(7, min_periods=1).mean()
        if "avg_waiting_hours" in df.columns:
            df["wait_ma7"] = df["avg_waiting_hours"].rolling(7, min_periods=1).mean()
        if "performance_score" in df.columns:
            df["perf_ma7"] = df["performance_score"].rolling(7, min_periods=1).mean()
        return df

    def kpis(self, b: PortBundle) -> dict[str, Any]:
        s = self.series_frame(b)
        latest = s.iloc[-1] if not s.empty else None
        ops0 = b.ops_risk.iloc[0] if not b.ops_risk.empty else None
        berth0 = b.berth.iloc[0] if not b.berth.empty else None
        out: dict[str, Any] = {
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "port": PORT,
            "metric_date": str(latest.get("metric_date").date())
            if latest is not None and pd.notna(latest.get("metric_date"))
            else None,
            "performance_score": _num(latest, "performance_score"),
            "congestion_index": _num(latest, "congestion_index"),
            "congestion_level": str(latest.get("congestion_level") or "") if latest is not None else "",
            "arrivals": int(_num(latest, "arrivals")),
            "departures": int(_num(latest, "departures")),
            "active_vessels": int(_num(latest, "active_vessels")),
            "avg_waiting_hours": _num(latest, "avg_waiting_hours"),
            "throughput": _num(latest, "throughput_proxy"),
            "balance_ratio": _num(latest, "balance_ratio"),
            "pressure_index": _num(berth0, "pressure_index"),
            "pressure_level": str(berth0.get("pressure_level") or "") if berth0 is not None else "",
            "occupancy_pct": _num(berth0, "occupancy_pct"),
            "capacity_proxy": int(_num(berth0, "capacity_proxy", default=45)),
            "ops_risk": _num(ops0, "composite_ops_risk"),
            "ops_level": str(ops0.get("risk_level") or "") if ops0 is not None else "",
            "drivers": str(ops0.get("drivers") or "") if ops0 is not None else "",
        }
        # outlook peaks
        if not b.congestion_fc.empty and "congestion_index_pred" in b.congestion_fc.columns:
            out["peak_congestion_fc"] = float(b.congestion_fc["congestion_index_pred"].max())
            peak_row = b.congestion_fc.loc[b.congestion_fc["congestion_index_pred"].idxmax()]
            out["peak_congestion_day"] = int(peak_row.get("horizon_day") or 0)
        if not b.arrival_fc.empty and "arrivals_pred" in b.arrival_fc.columns:
            out["peak_arrivals_fc"] = float(b.arrival_fc["arrivals_pred"].max())
        return out

    def period_compare(self, b: PortBundle, window: int = 7) -> pd.DataFrame:
        s = self.series_frame(b)
        if s.empty or len(s) < 2:
            return pd.DataFrame()
        cols = [
            c
            for c in (
                "arrivals",
                "departures",
                "active_vessels",
                "congestion_index",
                "avg_waiting_hours",
                "performance_score",
                "throughput_proxy",
            )
            if c in s.columns
        ]
        if not cols:
            return pd.DataFrame()
        recent = s.tail(window)
        prior = s.iloc[max(0, len(s) - 2 * window) : max(0, len(s) - window)]
        rows = []
        for c in cols:
            r = float(recent[c].mean()) if not recent.empty else np.nan
            p = float(prior[c].mean()) if not prior.empty else np.nan
            delta = r - p if pd.notna(r) and pd.notna(p) else np.nan
            pct = (delta / p * 100.0) if pd.notna(delta) and p not in (0, np.nan) and p != 0 else np.nan
            rows.append(
                {
                    "metric": c,
                    f"last_{window}d_avg": round(r, 2) if pd.notna(r) else None,
                    f"prior_{window}d_avg": round(p, 2) if pd.notna(p) else None,
                    "delta": round(delta, 2) if pd.notna(delta) else None,
                    "delta_pct": round(pct, 1) if pd.notna(pct) else None,
                }
            )
        return pd.DataFrame(rows)

    def weekday_profile(self, b: PortBundle) -> pd.DataFrame:
        s = self.series_frame(b)
        if s.empty:
            return pd.DataFrame()
        df = s.copy()
        df["weekday"] = df["metric_date"].dt.day_name()
        df["dow"] = df["metric_date"].dt.dayofweek
        agg_cols = [
            c
            for c in ("arrivals", "departures", "congestion_index", "avg_waiting_hours")
            if c in df.columns
        ]
        if not agg_cols:
            return pd.DataFrame()
        g = df.groupby(["dow", "weekday"], as_index=False)[agg_cols].mean()
        return g.sort_values("dow")

    def vessel_mix(self, b: PortBundle) -> pd.DataFrame:
        """Daily mix from performance/metrics + activity type counts."""
        rows = []
        s = self.series_frame(b)
        if not s.empty:
            latest = s.iloc[-1]
            typed = 0
            for label, key in (
                ("Container", "container_vessels"),
                ("Tanker", "tankers"),
                ("Fishing", "fishing_vessels"),
            ):
                if key in s.columns and pd.notna(latest.get(key)):
                    n = int(_num(latest, key))
                    typed += n
                    if n > 0:
                        rows.append(
                            {"category": label, "count": n, "source": "daily_metrics"}
                        )
            other = int(_num(latest, "active_vessels")) - typed
            if other > 0:
                rows.append(
                    {"category": "Other / general", "count": other, "source": "daily_metrics"}
                )
        if not b.activity.empty and "vessel_type" in b.activity.columns:
            vc = (
                b.activity["vessel_type"]
                .fillna("Unknown")
                .astype(str)
                .str.upper()
                .value_counts()
                .head(12)
            )
            for k, v in vc.items():
                rows.append({"category": str(k).title(), "count": int(v), "source": "activity_events"})
        return pd.DataFrame(rows)

    def flag_mix(self, b: PortBundle) -> pd.DataFrame:
        if b.activity.empty:
            return pd.DataFrame()
        col = "flag" if "flag" in b.activity.columns else None
        if not col:
            return pd.DataFrame()
        vc = b.activity[col].fillna("Unknown").astype(str).value_counts().reset_index()
        vc.columns = ["flag", "events"]
        vc["share_pct"] = (vc["events"] / vc["events"].sum() * 100).round(1)
        return vc

    def event_type_mix(self, b: PortBundle) -> pd.DataFrame:
        if b.activity.empty or "event_type" not in b.activity.columns:
            return pd.DataFrame()
        vc = b.activity["event_type"].fillna("Unknown").astype(str).value_counts().reset_index()
        vc.columns = ["event_type", "count"]
        return vc

    def wait_distribution(self, b: PortBundle) -> dict[str, float]:
        waits: list[float] = []
        if not b.activity.empty and "waiting_hours" in b.activity.columns:
            waits = [
                float(x)
                for x in pd.to_numeric(b.activity["waiting_hours"], errors="coerce").dropna().tolist()
            ]
        s = self.series_frame(b)
        if not waits and not s.empty and "avg_waiting_hours" in s.columns:
            waits = [
                float(x)
                for x in pd.to_numeric(s["avg_waiting_hours"], errors="coerce").dropna().tolist()
            ]
        if not waits:
            return {}
        arr = np.array(waits, dtype=float)
        return {
            "n": float(len(arr)),
            "mean": float(np.mean(arr)),
            "p50": float(np.percentile(arr, 50)),
            "p75": float(np.percentile(arr, 75)),
            "p90": float(np.percentile(arr, 90)),
            "p95": float(np.percentile(arr, 95)),
            "max": float(np.max(arr)),
        }

    def watchlist_alerts(self, b: PortBundle) -> pd.DataFrame:
        """Threshold-based operational alerts for the command center."""
        k = self.kpis(b)
        alerts = []
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        def add(sev: str, code: str, msg: str, value: float | None = None):
            alerts.append(
                {
                    "severity": sev,
                    "code": code,
                    "message": msg,
                    "value": value,
                    "as_of": now,
                }
            )

        cong = k.get("congestion_index") or 0
        if cong >= 80:
            add("CRITICAL", "CONGESTION_HIGH", f"Congestion index {cong:.0f} — severe delay risk", cong)
        elif cong >= 55:
            add("HIGH", "CONGESTION_ELEVATED", f"Congestion elevated at {cong:.0f}", cong)
        elif cong >= 40:
            add("WATCH", "CONGESTION_WATCH", f"Congestion on watch at {cong:.0f}", cong)

        wait = k.get("avg_waiting_hours") or 0
        if wait >= 24:
            add("CRITICAL", "WAIT_EXTREME", f"Average wait {wait:.1f}h exceeds 24h", wait)
        elif wait >= 12:
            add("HIGH", "WAIT_HIGH", f"Average wait {wait:.1f}h elevated", wait)
        elif wait >= 8:
            add("WATCH", "WAIT_WATCH", f"Average wait {wait:.1f}h", wait)

        press = k.get("pressure_index") or 0
        pl = (k.get("pressure_level") or "").upper()
        if pl in ("CRITICAL",) or press >= 75:
            add("CRITICAL", "BERTH_CRITICAL", f"Berth pressure critical ({press:.0f})", press)
        elif pl == "HIGH" or press >= 55:
            add("HIGH", "BERTH_HIGH", f"Berth pressure high ({press:.0f})", press)

        ops = k.get("ops_risk") or 0
        ol = (k.get("ops_level") or "").upper()
        if ol == "HIGH" or ops >= 70:
            add("HIGH", "OPS_RISK_HIGH", f"Composite ops risk {ops:.0f}", ops)
        elif ol == "MODERATE" or ops >= 45:
            add("WATCH", "OPS_RISK_MOD", f"Ops risk moderate ({ops:.0f})", ops)

        arr, dep = k.get("arrivals") or 0, k.get("departures") or 0
        gap = arr - dep
        if gap >= 6:
            add("HIGH", "INFLOW_SURGE", f"Arrival surplus +{gap} vs departures", float(gap))
        elif gap <= -6:
            add("WATCH", "OUTFLOW_HEAVY", f"Departure surplus {-gap} (clearing)", float(gap))

        peak = k.get("peak_congestion_fc")
        if peak is not None and peak >= 70:
            add(
                "WATCH",
                "FC_CONGESTION_PEAK",
                f"7d forecast peaks at {peak:.0f} on horizon day {k.get('peak_congestion_day')}",
                float(peak),
            )

        # activity spike vs series
        s = self.series_frame(b)
        if not s.empty and "arrivals" in s.columns and len(s) >= 8:
            mean7 = float(s["arrivals"].tail(7).mean())
            last = float(s["arrivals"].iloc[-1])
            if mean7 > 0 and last >= mean7 * 1.5:
                add("WATCH", "ARRIVAL_SPIKE", f"Latest arrivals {last:.0f} vs 7d avg {mean7:.1f}", last)

        if not alerts:
            add("INFO", "NOMINAL", "No threshold breaches — operations within watch bands", 0.0)

        order = {"CRITICAL": 0, "HIGH": 1, "WATCH": 2, "INFO": 3}
        df = pd.DataFrame(alerts)
        df["_o"] = df["severity"].map(order)
        return df.sort_values("_o").drop(columns="_o")

    def executive_brief(self, b: PortBundle) -> str:
        k = self.kpis(b)
        alerts = self.watchlist_alerts(b)
        top = alerts.iloc[0] if not alerts.empty else None
        cmp7 = self.period_compare(b, 7)
        cong_delta = ""
        if not cmp7.empty:
            row = cmp7[cmp7["metric"] == "congestion_index"]
            if not row.empty and pd.notna(row.iloc[0].get("delta")):
                d = float(row.iloc[0]["delta"])
                cong_delta = f" Congestion is {d:+.1f} vs the prior week."

        wait_txt = f"{k.get('avg_waiting_hours', 0):.1f}h average wait"
        peak_txt = ""
        if k.get("peak_congestion_fc") is not None:
            peak_txt = (
                f" Seven-day congestion outlook peaks near "
                f"**{k['peak_congestion_fc']:.0f}** (day {k.get('peak_congestion_day', '—')})."
            )

        sev = str(top["severity"]) if top is not None else "INFO"
        headline = {
            "CRITICAL": "Immediate attention required at Mombasa.",
            "HIGH": "Elevated operational pressure at Mombasa.",
            "WATCH": "Mombasa is on watch — manageable but tight.",
            "INFO": "Mombasa port operations look broadly stable.",
        }.get(sev, "Mombasa port status update.")

        return (
            f"**{headline}** "
            f"As of **{k.get('metric_date') or k.get('as_of')}**, performance score "
            f"**{k.get('performance_score', 0):.0f}**, congestion "
            f"**{k.get('congestion_index', 0):.0f}** ({k.get('congestion_level') or 'n/a'}), "
            f"berth pressure **{k.get('pressure_index', 0):.0f}** ({k.get('pressure_level') or 'n/a'}), "
            f"ops risk **{k.get('ops_risk', 0):.0f}** ({k.get('ops_level') or 'n/a'}). "
            f"Latest day: **{k.get('arrivals', 0)}** arrivals / **{k.get('departures', 0)}** departures, "
            f"{wait_txt}.{cong_delta}{peak_txt} "
            f"Primary signal: _{top['message'] if top is not None else 'n/a'}_. "
            f"Drivers: `{k.get('drivers') or 'n/a'}`."
        )

    def whatif(
        self,
        b: PortBundle,
        extra_arrivals: float = 0.0,
        capacity_delta: float = 0.0,
        wait_shock_h: float = 0.0,
    ) -> dict[str, Any]:
        """Simple sensitivity model on top of latest snapshot (planning aid)."""
        k = self.kpis(b)
        base_arr = float(k.get("arrivals") or 0)
        base_dep = float(k.get("departures") or 0)
        base_active = float(k.get("active_vessels") or 0)
        base_wait = float(k.get("avg_waiting_hours") or 0)
        base_cong = float(k.get("congestion_index") or 0)
        cap = float(k.get("capacity_proxy") or 45) + capacity_delta
        cap = max(5.0, cap)

        sim_arr = max(0.0, base_arr + extra_arrivals)
        sim_active = max(0.0, base_active + extra_arrivals * 0.7 - max(0.0, -extra_arrivals) * 0.3)
        sim_wait = max(0.0, base_wait + wait_shock_h + max(0.0, extra_arrivals) * 0.8 - capacity_delta * 0.15)
        # congestion responds to occupancy + wait + inflow gap
        occ = min(160.0, 100.0 * sim_active / cap)
        gap = sim_arr - base_dep
        sim_cong = max(
            0.0,
            min(
                100.0,
                base_cong * 0.35 + occ * 0.35 + min(30.0, sim_wait * 2.2) + min(20.0, max(0.0, gap) * 2.5),
            ),
        )
        pressure = min(100.0, occ * 0.7 + min(30.0, sim_wait * 3) + min(20.0, max(0.0, gap) * 4))
        perf = 100.0 - min(40.0, sim_cong * 0.35) - min(25.0, sim_wait * 2.0) + min(15.0, (sim_arr + base_dep) * 0.3)
        perf = max(0.0, min(100.0, perf))

        def level(idx: float) -> str:
            if idx >= 80:
                return "HIGH"
            if idx >= 55:
                return "MODERATE"
            if idx >= 30:
                return "LOW"
            return "CLEAR"

        def plevel(p: float) -> str:
            if p >= 75:
                return "CRITICAL"
            if p >= 55:
                return "HIGH"
            if p >= 35:
                return "MODERATE"
            return "LOW"

        return {
            "base": {
                "arrivals": base_arr,
                "active": base_active,
                "wait_h": base_wait,
                "congestion": base_cong,
                "pressure": float(k.get("pressure_index") or 0),
                "performance": float(k.get("performance_score") or 0),
                "capacity": float(k.get("capacity_proxy") or 45),
            },
            "sim": {
                "arrivals": round(sim_arr, 1),
                "active": round(sim_active, 1),
                "wait_h": round(sim_wait, 1),
                "congestion": round(sim_cong, 1),
                "congestion_level": level(sim_cong),
                "pressure": round(pressure, 1),
                "pressure_level": plevel(pressure),
                "performance": round(perf, 1),
                "occupancy_pct": round(occ, 1),
                "capacity": round(cap, 1),
            },
            "delta": {
                "congestion": round(sim_cong - base_cong, 1),
                "pressure": round(pressure - float(k.get("pressure_index") or 0), 1),
                "wait_h": round(sim_wait - base_wait, 1),
                "performance": round(perf - float(k.get("performance_score") or 0), 1),
            },
        }

    def near_port_ais(self, hours: int = 48, limit: int = 400) -> pd.DataFrame:
        """Latest AIS positions roughly near Mombasa (if fact_ais_positions exists)."""
        if not self.table_exists("fact_ais_positions"):
            return pd.DataFrame()
        # Column discovery
        cols_df = self.qdf(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='fact_ais_positions'
            """
        )
        if cols_df.empty:
            return pd.DataFrame()
        cols = set(cols_df["column_name"].str.lower())
        lat_c = next((c for c in ("lat", "latitude", "position_lat") if c in cols), None)
        lon_c = next((c for c in ("lon", "lng", "longitude", "position_lon") if c in cols), None)
        ts_c = next(
            (c for c in ("ts", "event_time", "position_time", "msg_time", "created_at") if c in cols),
            None,
        )
        if not lat_c or not lon_c:
            return pd.DataFrame()

        # Degree box ~ radius (1 deg lat ~ 60nm; lon scaled near equator)
        dlat = MOM_RADIUS_NM / 60.0
        dlon = MOM_RADIUS_NM / (60.0 * max(0.2, math.cos(math.radians(MOM_LAT))))
        time_filter = ""
        if ts_c:
            time_filter = f"AND {ts_c} >= NOW() - INTERVAL '{int(hours)} hours'"

        mmsi_c = "mmsi" if "mmsi" in cols else None
        name_c = next((c for c in ("vessel_name", "shipname", "name") if c in cols), None)
        sog_c = next((c for c in ("sog", "speed", "speed_knots") if c in cols), None)
        type_c = next((c for c in ("vessel_type", "ship_type", "type_name") if c in cols), None)

        select_bits = [f"{lat_c} AS lat", f"{lon_c} AS lon"]
        if ts_c:
            select_bits.append(f"{ts_c} AS ts")
        if mmsi_c:
            select_bits.append(f"{mmsi_c} AS mmsi")
        if name_c:
            select_bits.append(f"{name_c} AS vessel_name")
        if sog_c:
            select_bits.append(f"{sog_c} AS sog")
        if type_c:
            select_bits.append(f"{type_c} AS vessel_type")

        order = f"ORDER BY {ts_c} DESC NULLS LAST" if ts_c else ""
        sql = f"""
            SELECT {", ".join(select_bits)}
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
                "lat0": MOM_LAT - dlat,
                "lat1": MOM_LAT + dlat,
                "lon0": MOM_LON - dlon,
                "lon1": MOM_LON + dlon,
                "lim": int(limit),
            },
        )
        if df.empty:
            return df
        # Haversine filter to circular radius
        def hav_nm(lat, lon) -> float:
            r = 6371.0
            p1, p2 = math.radians(MOM_LAT), math.radians(float(lat))
            dphi = math.radians(float(lat) - MOM_LAT)
            dl = math.radians(float(lon) - MOM_LON)
            a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
            km = 2 * r * math.asin(min(1.0, math.sqrt(a)))
            return km / 1.852

        df["dist_nm"] = [
            hav_nm(a, b) if pd.notna(a) and pd.notna(b) else np.nan
            for a, b in zip(df["lat"], df["lon"])
        ]
        df = df[df["dist_nm"] <= MOM_RADIUS_NM].copy()
        if "mmsi" in df.columns:
            # latest per MMSI
            if "ts" in df.columns:
                df = df.sort_values("ts", ascending=False)
            df = df.drop_duplicates(subset=["mmsi"], keep="first")
        return df.reset_index(drop=True)

    def turnaround_proxy(self, b: PortBundle) -> pd.DataFrame:
        """Turnaround / dwell proxy.

        Prefer paired arrival→departure by MMSI. If the seed is one-row-per-MMSI
        (common), fall back to dwell_hours / waiting_hours on each event.
        """
        act = b.activity
        if act.empty:
            return pd.DataFrame()
        df = act.copy()
        df["event_time"] = pd.to_datetime(df.get("event_time"), errors="coerce")
        if "event_type" in df.columns:
            df["event_type"] = df["event_type"].astype(str).str.upper()

        rows: list[dict] = []
        if "mmsi" in df.columns and "event_type" in df.columns:
            for mmsi, g in df.dropna(subset=["event_time"]).groupby("mmsi"):
                g = g.sort_values("event_time")
                arrivals = g[g["event_type"].str.contains("ARR", na=False)]
                deps = g[g["event_type"].str.contains("DEP", na=False)]
                if arrivals.empty or deps.empty:
                    continue
                for _, ar in arrivals.iterrows():
                    later = deps[deps["event_time"] > ar["event_time"]]
                    if later.empty:
                        continue
                    dep = later.iloc[0]
                    hours = (dep["event_time"] - ar["event_time"]).total_seconds() / 3600.0
                    if 0 < hours < 240:
                        rows.append(
                            {
                                "mmsi": mmsi,
                                "vessel_name": ar.get("vessel_name") or dep.get("vessel_name"),
                                "vessel_type": ar.get("vessel_type") or dep.get("vessel_type"),
                                "flag": ar.get("flag") or dep.get("flag"),
                                "arrival": ar["event_time"],
                                "departure": dep["event_time"],
                                "turnaround_hours": round(hours, 1),
                                "source": "paired_events",
                            }
                        )
                    break

        if rows:
            return pd.DataFrame(rows).sort_values("turnaround_hours", ascending=False)

        # Fallback: dwell per event
        wait_col = None
        for c in ("waiting_hours", "dwell_hours"):
            if c in df.columns:
                wait_col = c
                break
        if not wait_col:
            return pd.DataFrame()
        tmp = df.copy()
        tmp["turnaround_hours"] = pd.to_numeric(tmp[wait_col], errors="coerce")
        tmp = tmp[tmp["turnaround_hours"].notna() & (tmp["turnaround_hours"] > 0)]
        if tmp.empty:
            return pd.DataFrame()
        keep = [
            c
            for c in (
                "mmsi",
                "vessel_name",
                "vessel_type",
                "flag",
                "event_type",
                "event_time",
                "turnaround_hours",
            )
            if c in tmp.columns
        ]
        out = tmp[keep].copy()
        out["source"] = f"event_{wait_col}"
        if "event_time" in out.columns:
            out = out.rename(columns={"event_time": "arrival"})
        return out.sort_values("turnaround_hours", ascending=False)

    def efficiency_scorecard(self, b: PortBundle) -> pd.DataFrame:
        k = self.kpis(b)
        wait = self.wait_distribution(b)
        cmp7 = self.period_compare(b, 7)

        def delta_for(metric: str) -> float | None:
            if cmp7.empty:
                return None
            row = cmp7[cmp7["metric"] == metric]
            if row.empty:
                return None
            v = row.iloc[0].get("delta_pct")
            return float(v) if pd.notna(v) else None

        cards = [
            {
                "pillar": "Throughput",
                "score": min(100.0, (k.get("throughput") or 0) * 4.0),
                "detail": f"{k.get('arrivals', 0)} in / {k.get('departures', 0)} out",
                "wow_pct": delta_for("throughput_proxy") or delta_for("arrivals"),
            },
            {
                "pillar": "Fluidity",
                "score": max(0.0, 100.0 - (k.get("avg_waiting_hours") or 0) * 4.0),
                "detail": f"wait mean {wait.get('mean', k.get('avg_waiting_hours', 0)):.1f}h · p90 {wait.get('p90', float('nan')):.1f}h"
                if wait
                else f"wait {k.get('avg_waiting_hours', 0):.1f}h",
                "wow_pct": delta_for("avg_waiting_hours"),
            },
            {
                "pillar": "Congestion control",
                "score": max(0.0, 100.0 - (k.get("congestion_index") or 0)),
                "detail": f"index {k.get('congestion_index', 0):.0f} · {k.get('congestion_level') or 'n/a'}",
                "wow_pct": delta_for("congestion_index"),
            },
            {
                "pillar": "Berth utilisation",
                "score": max(0.0, 100.0 - abs((k.get("occupancy_pct") or 0) - 70) * 1.2),
                "detail": f"occupancy {k.get('occupancy_pct', 0):.0f}% · pressure {k.get('pressure_index', 0):.0f}",
                "wow_pct": None,
            },
            {
                "pillar": "Ops risk posture",
                "score": max(0.0, 100.0 - (k.get("ops_risk") or 0)),
                "detail": f"composite {k.get('ops_risk', 0):.0f} · {k.get('ops_level') or 'n/a'}",
                "wow_pct": None,
            },
        ]
        for c in cards:
            c["score"] = round(float(c["score"]), 1)
        return pd.DataFrame(cards)

    def export_pack(self, b: PortBundle) -> dict[str, pd.DataFrame]:
        return {
            "performance": self.series_frame(b),
            "congestion_forecast": b.congestion_fc,
            "arrival_forecast": b.arrival_fc,
            "berth_pressure": b.berth,
            "ops_risk": b.ops_risk,
            "activity": b.activity,
            "period_compare_7d": self.period_compare(b, 7),
            "weekday_profile": self.weekday_profile(b),
            "alerts": self.watchlist_alerts(b),
            "vessel_mix": self.vessel_mix(b),
            "flag_mix": self.flag_mix(b),
            "turnaround": self.turnaround_proxy(b),
            "scorecard": self.efficiency_scorecard(b),
        }


def get_service() -> PortIntelligenceService:
    return PortIntelligenceService()

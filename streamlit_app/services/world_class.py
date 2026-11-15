"""
World-class ops layer for OceanWatch.

Situation fusion, decision cards, intelligence copilot answers,
global pulse, and narrative briefs — multi-domain, Kenya-first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
from sqlalchemy import text


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _qdf(engine, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    try:
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def _scalar(engine, sql: str, default: Any = 0, params: Optional[dict] = None) -> Any:
    df = _qdf(engine, sql, params)
    if df.empty:
        return default
    v = df.iloc[0, 0]
    return default if v is None or (isinstance(v, float) and pd.isna(v)) else v


@dataclass
class DecisionCard:
    urgency: str  # CRITICAL | HIGH | WATCH | INFO
    domain: str
    title: str
    why: str
    action: str
    page_hint: str = ""
    score: float = 0.0


@dataclass
class Pulse:
    overall: str = "UNKNOWN"  # GREEN | AMBER | RED
    score: float = 50.0
    label: str = "Assessing…"
    vessels: int = 0
    alerts_24h: int = 0
    port_risk: str = "—"
    port_score: float = 0.0
    ocean_hint: str = "—"
    freshness_ok: int = 0
    freshness_total: int = 0
    generated_at: str = ""
    domains: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pulse / fusion
# ---------------------------------------------------------------------------
def global_pulse(engine) -> Pulse:
    now = _utcnow()
    p = Pulse(generated_at=now.isoformat())

    p.vessels = int(
        _scalar(
            engine,
            """
            SELECT COUNT(DISTINCT CAST(mmsi AS TEXT))
            FROM fact_ais_positions
            WHERE COALESCE(event_time, ts, timestamp) > NOW() - INTERVAL '24 hours'
            """,
            0,
        )
        or _scalar(engine, "SELECT COUNT(DISTINCT mmsi) FROM fact_vessel_profiles", 0)
        or 0
    )

    p.alerts_24h = int(
        _scalar(
            engine,
            """
            SELECT COUNT(*) FROM fact_alerts
            WHERE COALESCE(created_at, detected_at, ts) > NOW() - INTERVAL '24 hours'
            """,
            0,
        )
        or _scalar(
            engine,
            """
            SELECT COUNT(*) FROM fact_vessel_anomalies
            WHERE COALESCE(detected_at, created_at) > NOW() - INTERVAL '24 hours'
            """,
            0,
        )
        or 0
    )

    ops = _qdf(
        engine,
        """
        SELECT composite_ops_risk, risk_level, drivers
        FROM fact_port_ops_risk
        ORDER BY as_of DESC NULLS LAST
        LIMIT 1
        """,
    )
    if not ops.empty:
        p.port_score = float(ops.iloc[0].get("composite_ops_risk") or 0)
        p.port_risk = str(ops.iloc[0].get("risk_level") or "—")
        p.domains["port"] = {
            "score": p.port_score,
            "level": p.port_risk,
            "drivers": ops.iloc[0].get("drivers"),
        }

    cong = _scalar(
        engine,
        """
        SELECT congestion_index FROM fact_port_performance
        ORDER BY metric_date DESC NULLS LAST LIMIT 1
        """,
        None,
    )
    if cong is not None:
        p.domains["congestion"] = float(cong)

    sst = _qdf(
        engine,
        """
        SELECT sst_celsius, obs_date FROM fact_sst_daily
        ORDER BY obs_date DESC NULLS LAST LIMIT 1
        """,
    )
    if sst.empty:
        sst = _qdf(
            engine,
            """
            SELECT mean_sst_c AS sst_celsius, index_date AS obs_date
            FROM fact_ocean_index
            ORDER BY index_date DESC NULLS LAST LIMIT 1
            """,
        )
    if not sst.empty and pd.notna(sst.iloc[0].get("sst_celsius")):
        p.ocean_hint = f"SST {float(sst.iloc[0]['sst_celsius']):.1f}°C"
        p.domains["sst"] = float(sst.iloc[0]["sst_celsius"])

    # Freshness probes (best-effort)
    probes = [
        ("fact_ais_positions", "COALESCE(event_time, ts, timestamp)"),
        ("fact_port_ops_risk", "as_of"),
        ("fact_alerts", "COALESCE(created_at, detected_at)"),
        ("fact_sst_daily", "obs_date"),
        ("fact_vessel_profiles", "COALESCE(updated_at, created_at)"),
        ("fact_port_performance", "metric_date"),
    ]
    ok = 0
    total = 0
    for table, col in probes:
        total += 1
        n = _scalar(
            engine,
            f"""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema='public' AND table_name='{table}'
            """,
            0,
        )
        if not n:
            continue
        age_ok = _scalar(
            engine,
            f"""
            SELECT CASE WHEN MAX({col}) > NOW() - INTERVAL '48 hours' THEN 1 ELSE 0 END
            FROM {table}
            """,
            0,
        )
        # date columns may need cast
        if not age_ok:
            age_ok = _scalar(
                engine,
                f"""
                SELECT CASE WHEN MAX({col}::timestamp) > NOW() - INTERVAL '72 hours'
                       THEN 1 ELSE 0 END
                FROM {table}
                """,
                0,
            )
        ok += int(age_ok or 0)
    p.freshness_ok = ok
    p.freshness_total = total

    # Composite score (lower risk = greener inverted for display as health)
    risk_load = 0.0
    risk_load += min(40.0, p.port_score * 0.4)
    risk_load += min(30.0, p.alerts_24h * 3.0)
    if p.freshness_total:
        fresh_ratio = p.freshness_ok / max(1, p.freshness_total)
        risk_load += (1.0 - fresh_ratio) * 25.0
    health = max(0.0, min(100.0, 100.0 - risk_load))
    p.score = round(health, 1)
    if health >= 75:
        p.overall = "GREEN"
        p.label = "Situation stable"
    elif health >= 50:
        p.overall = "AMBER"
        p.label = "Elevated attention"
    else:
        p.overall = "RED"
        p.label = "Priority response"
    return p


def decision_cards(engine, pulse: Optional[Pulse] = None) -> list[DecisionCard]:
    pulse = pulse or global_pulse(engine)
    cards: list[DecisionCard] = []

    if pulse.port_score >= 70:
        cards.append(
            DecisionCard(
                urgency="CRITICAL",
                domain="Port",
                title="Mombasa ops risk elevated",
                why=f"Composite ops risk {pulse.port_score:.0f} ({pulse.port_risk}). "
                f"{(pulse.domains.get('port') or {}).get('drivers') or ''}",
                action="Open Port Intelligence — review berth pressure & arrival forecast; "
                "notify harbour ops if occupancy > capacity proxy.",
                page_hint="Port Intelligence — Mombasa",
                score=pulse.port_score,
            )
        )
    elif pulse.port_score >= 45:
        cards.append(
            DecisionCard(
                urgency="HIGH",
                domain="Port",
                title="Watch Mombasa congestion",
                why=f"Ops risk {pulse.port_score:.0f} · congestion watch window.",
                action="Compare 7-day congestion forecast vs arrivals; stagger non-critical calls.",
                page_hint="Port Intelligence — Mombasa",
                score=pulse.port_score,
            )
        )

    if pulse.alerts_24h >= 8:
        cards.append(
            DecisionCard(
                urgency="HIGH",
                domain="Alerts",
                title=f"{pulse.alerts_24h} alerts in 24h",
                why="Alert volume above quiet baseline — possible clustering.",
                action="Triage Anomaly Engine + Event Bus; pin top MMSIs to watchlist.",
                page_hint="Anomaly Engine",
                score=min(100.0, pulse.alerts_24h * 5),
            )
        )
    elif pulse.alerts_24h >= 3:
        cards.append(
            DecisionCard(
                urgency="WATCH",
                domain="Alerts",
                title=f"{pulse.alerts_24h} recent alerts",
                why="Moderate alert activity in the last day.",
                action="Scan alert feed; confirm false positives vs true maritime events.",
                page_hint="Alerts",
                score=30.0,
            )
        )

    if pulse.vessels == 0:
        cards.append(
            DecisionCard(
                urgency="HIGH",
                domain="AIS",
                title="No AIS vessels in 24h window",
                why="Fleet picture empty — ingestion gap or API key.",
                action="Run `python ingestion/run_vessel_tracking.py` or fetch_ais_realtime.py.",
                page_hint="Vessel Tracking & AIS Analytics",
                score=80.0,
            )
        )
    elif pulse.vessels < 5:
        cards.append(
            DecisionCard(
                urgency="WATCH",
                domain="AIS",
                title="Thin AIS coverage",
                why=f"Only {pulse.vessels} distinct MMSIs in 24h.",
                action="Validate AISStream key / seed sample for demos.",
                page_hint="AIS Live",
                score=40.0,
            )
        )
    else:
        cards.append(
            DecisionCard(
                urgency="INFO",
                domain="AIS",
                title=f"{pulse.vessels} vessels tracked (24h)",
                why="AIS picture populated for Kenya / WIO box.",
                action="Filter dark cues & loiter flags on Vessel Tracking map.",
                page_hint="Vessel Tracking & AIS Analytics",
                score=10.0,
            )
        )

    if pulse.freshness_total and pulse.freshness_ok < max(2, pulse.freshness_total // 2):
        cards.append(
            DecisionCard(
                urgency="HIGH",
                domain="Data",
                title="Stale warehouse domains",
                why=f"Freshness {pulse.freshness_ok}/{pulse.freshness_total} tables within 48–72h.",
                action="Open Data Health / Platform Ops; re-run phase jobs for red domains.",
                page_hint="Data Health",
                score=70.0,
            )
        )

    # Dark / loiter proxy
    dark = int(
        _scalar(
            engine,
            """
            SELECT COUNT(*) FROM fact_vessel_profiles
            WHERE COALESCE(risk_score, behaviour_score, 0) >= 70
            """,
            0,
        )
        or 0
    )
    if dark >= 3:
        cards.append(
            DecisionCard(
                urgency="HIGH",
                domain="Risk",
                title=f"{dark} high-risk vessel profiles",
                why="Behaviour / risk scores ≥ 70 on profiles.",
                action="Replay tracks for top MMSIs; check MPA / loiter geofences.",
                page_hint="Vessel Tracking & AIS Analytics",
                score=min(100.0, 50 + dark * 5),
            )
        )

    if "sst" in pulse.domains and pulse.domains["sst"] >= 29.5:
        cards.append(
            DecisionCard(
                urgency="WATCH",
                domain="Ocean",
                title="Warm SST anomaly cue",
                why=f"{pulse.ocean_hint} — thermal stress / bloom watch for coastal ops.",
                action="Cross-check Bloom Risk and Habitat Suitability pages.",
                page_hint="Bloom Risk",
                score=35.0,
            )
        )

    if not cards:
        cards.append(
            DecisionCard(
                urgency="INFO",
                domain="Ops",
                title="No priority cards",
                why="Fusion engine found no elevated drivers.",
                action="Continue routine Kenya EEZ Today patrol checklist.",
                page_hint="Kenya EEZ Today",
                score=0.0,
            )
        )

    order = {"CRITICAL": 0, "HIGH": 1, "WATCH": 2, "INFO": 3}
    cards.sort(key=lambda c: (order.get(c.urgency, 9), -c.score))
    return cards


def narrative_brief(engine, pulse: Optional[Pulse] = None, cards: Optional[list[DecisionCard]] = None) -> str:
    pulse = pulse or global_pulse(engine)
    cards = cards or decision_cards(engine, pulse)
    now = _utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# OceanWatch Situation Brief — Kenya / WIO",
        f"**Generated:** {now}",
        f"**Overall:** {pulse.overall} ({pulse.score:.0f}/100) — {pulse.label}",
        "",
        "## Snapshot",
        f"- AIS vessels (24h): **{pulse.vessels}**",
        f"- Alerts / anomalies (24h): **{pulse.alerts_24h}**",
        f"- Mombasa ops risk: **{pulse.port_score:.0f}** ({pulse.port_risk})",
        f"- Ocean: **{pulse.ocean_hint}**",
        f"- Data freshness: **{pulse.freshness_ok}/{pulse.freshness_total}** domains recent",
        "",
        "## Priority decisions",
    ]
    for i, c in enumerate(cards[:8], 1):
        lines.append(f"{i}. **[{c.urgency}] {c.title}** ({c.domain})")
        lines.append(f"   - Why: {c.why}")
        lines.append(f"   - Action: {c.action}")
        if c.page_hint:
            lines.append(f"   - Open: {c.page_hint}")
    lines += [
        "",
        "## Operator notes",
        "- Scores are decision-support heuristics, not legal or official KPA figures.",
        "- Re-run vessel / port / ocean jobs before executive briefings.",
        "",
        "— OceanWatch AI · World-class ops layer",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Intelligence copilot (deterministic, data-backed)
# ---------------------------------------------------------------------------
_COPILOT_HINTS = [
    "How is Mombasa port right now?",
    "Any high-risk vessels?",
    "What should I do first?",
    "AIS coverage today?",
    "Is the data fresh?",
    "Ocean / SST status?",
    "Write me a situation brief",
    "Congestion forecast?",
]


def copilot_answer(engine, question: str) -> dict[str, Any]:
    q = (question or "").strip().lower()
    pulse = global_pulse(engine)
    cards = decision_cards(engine, pulse)
    out: dict[str, Any] = {
        "question": question,
        "answer": "",
        "evidence": {},
        "suggested_pages": [],
        "cards": cards[:5],
        "pulse": pulse,
    }

    if not q:
        out["answer"] = "Ask about port risk, AIS coverage, alerts, SST, freshness, or “what should I do first?”"
        return out

    if any(w in q for w in ("brief", "summary", "situation", "overview", "report")):
        out["answer"] = narrative_brief(engine, pulse, cards)
        out["suggested_pages"] = ["Command Center", "Kenya EEZ Today"]
        return out

    if any(w in q for w in ("first", "priority", "should i", "do next", "action", "recommend")):
        top = cards[0]
        out["answer"] = (
            f"**First action:** {top.action}\n\n"
            f"Driver: [{top.urgency}] {top.title} — {top.why}"
        )
        out["suggested_pages"] = [top.page_hint] if top.page_hint else []
        return out

    if any(w in q for w in ("mombasa", "port", "berth", "congestion", "arrival")):
        fc = _qdf(
            engine,
            """
            SELECT horizon_day, congestion_index_pred, congestion_level
            FROM fact_port_congestion_forecast
            ORDER BY horizon_day LIMIT 7
            """,
        )
        arr = _qdf(
            engine,
            """
            SELECT horizon_day, arrivals_pred
            FROM fact_port_arrival_forecast
            ORDER BY horizon_day LIMIT 7
            """,
        )
        berth = _qdf(
            engine,
            "SELECT * FROM fact_berth_pressure ORDER BY as_of DESC LIMIT 1",
        )
        parts = [
            f"Mombasa ops risk is **{pulse.port_score:.0f}** ({pulse.port_risk}).",
        ]
        if not berth.empty:
            b = berth.iloc[0]
            parts.append(
                f"Berth pressure **{float(b.get('pressure_index') or 0):.0f}** "
                f"({b.get('pressure_level')}), occupancy "
                f"**{float(b.get('occupancy_pct') or 0):.0f}%** "
                f"({int(b.get('active_vessels') or 0)}/{int(b.get('capacity_proxy') or 0)})."
            )
        if not fc.empty:
            peak = fc.loc[fc["congestion_index_pred"].idxmax()]
            parts.append(
                f"Congestion forecast peaks near day **{int(peak['horizon_day'])}** "
                f"at **{float(peak['congestion_index_pred']):.0f}** ({peak.get('congestion_level')})."
            )
        if not arr.empty:
            parts.append(
                f"Arrival outlook avg **{float(arr['arrivals_pred'].mean()):.1f}**/day next week."
            )
        out["answer"] = " ".join(parts)
        out["evidence"] = {
            "congestion_fc": fc.to_dict("records") if not fc.empty else [],
            "arrival_fc": arr.to_dict("records") if not arr.empty else [],
        }
        out["suggested_pages"] = ["Port Intelligence — Mombasa", "Port Risk"]
        return out

    if any(w in q for w in ("ais", "vessel", "ship", "fleet", "mmsi", "track", "dark", "loiter")):
        hi = int(
            _scalar(
                engine,
                """
                SELECT COUNT(*) FROM fact_vessel_profiles
                WHERE COALESCE(risk_score, behaviour_score, 0) >= 70
                """,
                0,
            )
            or 0
        )
        out["answer"] = (
            f"**{pulse.vessels}** distinct vessels in the recent AIS window. "
            f"**{hi}** profiles score high-risk (≥70). "
            "Open Vessel Tracking for map filters (type, flag, speed) and dark/loiter flags."
        )
        out["suggested_pages"] = ["Vessel Tracking & AIS Analytics", "AIS Live"]
        return out

    if any(w in q for w in ("alert", "anomal", "risk", "event")):
        out["answer"] = (
            f"**{pulse.alerts_24h}** alert/anomaly rows in ~24h. "
            "Triage via Anomaly Engine and Event Bus; pin MMSIs to the mission watchlist."
        )
        out["suggested_pages"] = ["Anomaly Engine", "Event Bus", "Alerts"]
        return out

    if any(w in q for w in ("fresh", "stale", "data quality", "health", "ingest")):
        out["answer"] = (
            f"Warehouse freshness probe: **{pulse.freshness_ok}/{pulse.freshness_total}** "
            "key tables look recent (48–72h). "
            "If red, re-run phase jobs from Platform Ops / Data Health."
        )
        out["suggested_pages"] = ["Data Health", "Platform Ops"]
        return out

    if any(w in q for w in ("ocean", "sst", "sea", "temp", "bloom", "tide", "swim")):
        out["answer"] = (
            f"Ocean cue: **{pulse.ocean_hint}**. "
            "Use Kenya EEZ Today for tides/swim windows; Bloom Risk and Habitat for biophysical stress."
        )
        out["suggested_pages"] = ["Kenya EEZ Today", "Bloom Risk", "Coastal Tides"]
        return out

    if any(w in q for w in ("fish", "gfw", "iui", "illegal")):
        out["answer"] = (
            "Fishing picture: open Fishing Activity and GFW Fishing Effort for effort cells, "
            "plus Fisheries Intelligence for IUU-oriented risk layers. "
            "GFW is decision-support only — not a legal determination."
        )
        out["suggested_pages"] = ["GFW Fishing Effort", "Fisheries Intelligence"]
        return out

    # Default: pulse + top cards
    top_lines = "\n".join(f"- [{c.urgency}] {c.title}" for c in cards[:4])
    out["answer"] = (
        f"Overall **{pulse.overall}** ({pulse.score:.0f}/100) — {pulse.label}.\n\n"
        f"Top drivers:\n{top_lines}\n\n"
        "Try: “How is Mombasa port?”, “Any high-risk vessels?”, or “Write me a situation brief”."
    )
    out["suggested_pages"] = ["Command Center", "Watch Floor"]
    return out


def benchmark_snapshot(engine) -> pd.DataFrame:
    """Simple Kenya-centric benchmark strip (port + AIS + risk)."""
    rows = []
    pulse = global_pulse(engine)
    rows.append(
        {
            "domain": "Situation health",
            "metric": pulse.score,
            "unit": "/100",
            "status": pulse.overall,
            "peer_note": "Internal multi-domain fusion",
        }
    )
    rows.append(
        {
            "domain": "Mombasa ops risk",
            "metric": pulse.port_score,
            "unit": "index",
            "status": pulse.port_risk,
            "peer_note": "vs capacity proxy 45 vessels",
        }
    )
    rows.append(
        {
            "domain": "AIS vessels 24h",
            "metric": pulse.vessels,
            "unit": "MMSIs",
            "status": "OK" if pulse.vessels >= 5 else "THIN",
            "peer_note": "Kenya EEZ / WIO box",
        }
    )
    rows.append(
        {
            "domain": "Alerts 24h",
            "metric": pulse.alerts_24h,
            "unit": "events",
            "status": "HOT" if pulse.alerts_24h >= 8 else "QUIET",
            "peer_note": "Unified + vessel anomalies",
        }
    )
    cong = pulse.domains.get("congestion")
    if cong is not None:
        rows.append(
            {
                "domain": "Port congestion",
                "metric": cong,
                "unit": "index",
                "status": "HIGH" if cong >= 70 else "MOD" if cong >= 45 else "LOW",
                "peer_note": "Mombasa daily series",
            }
        )
    return pd.DataFrame(rows)

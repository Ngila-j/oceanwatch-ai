"""Vessel Intelligence — behaviour scores, risk tiers, anomalies."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_APP = Path(__file__).resolve().parents[1]
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from components.pagekit import boot, close_page  # noqa: E402
from components.ui import banner, kpi_row  # noqa: E402

try:
    from services.vessel_tracking import VesselTrackingService
except ImportError:  # pragma: no cover
    from streamlit_app.services.vessel_tracking import VesselTrackingService  # type: ignore


def _resolve_db_uri() -> str:
    try:
        import sys as _sys
        from pathlib import Path as _P

        ing = _P(__file__).resolve().parents[2] / "ingestion"
        if str(ing) not in _sys.path:
            _sys.path.insert(0, str(ing))
        from db_utils import get_db_uri as _ing  # type: ignore

        return _ing()
    except Exception:  # noqa: BLE001
        pass
    try:
        from db_config import get_db_uri

        return get_db_uri()
    except Exception:  # noqa: BLE001
        from streamlit_app.db_config import get_db_uri  # type: ignore

        return get_db_uri()


boot(
    "Vessel Intelligence",
    "Behaviour scores, risk tiers, loitering / dark cues, and anomaly flags for Kenya EEZ traffic.",
    chips=[("Phase 12", "info"), ("Maritime", "primary")],
)


@st.cache_resource(show_spinner=False)
def _svc() -> VesselTrackingService:
    return VesselTrackingService(db_uri=_resolve_db_uri())


with st.sidebar:
    st.markdown("### Scope")
    hours = st.slider("Lookback (hours)", 24, 336, 168, 24)
    only_kenya = st.checkbox("Kenya / WIO profiles only", value=True)
    min_risk = st.slider("Min risk score", 0, 100, 40, 5)
    search = st.text_input("Filter MMSI / name", "")

svc = _svc()
snap = svc.snapshot(hours=hours, only_kenya=only_kenya, search=search or None)
k = svc.kpis(snap)

kpi_row(
    [
        {
            "label": "Profiles",
            "value": f"{k['vessels']:,}",
            "hint": "fact_vessel_profiles",
            "tone": "primary",
        },
        {
            "label": "High-risk behaviour",
            "value": f"{k['high_risk_behaviour']:,}",
            "hint": "score ≥ 70",
            "tone": "danger" if k["high_risk_behaviour"] else "success",
        },
        {
            "label": "Anomalies",
            "value": f"{k['anomalies']:,}",
            "hint": f"last {hours}h",
            "tone": "warning" if k["anomalies"] else "info",
        },
        {
            "label": "Geofence hits",
            "value": f"{k['geofence_events']:,}",
            "hint": "crossings / dwell",
            "tone": "warning" if k["geofence_events"] else "info",
        },
    ]
)

if snap.errors:
    for e in snap.errors:
        banner("Vessel data missing", str(e), tone="warning")

tab_risk, tab_beh, tab_anom, tab_geo = st.tabs(
    ["Risk roster", "Behaviour scores", "Anomalies", "Geofence intel"]
)

vessels = snap.vessels if snap.vessels is not None else pd.DataFrame()
beh = snap.behaviour if snap.behaviour is not None else pd.DataFrame()
anom = snap.anomalies if snap.anomalies is not None else pd.DataFrame()
gf = snap.geofence_events if snap.geofence_events is not None else pd.DataFrame()

with tab_risk:
    st.markdown("#### Vessel risk roster")
    if vessels.empty:
        st.info(
            "No profiles yet. Run `python ingestion/run_vessel_tracking.py` after AIS is loaded."
        )
    else:
        view = vessels.copy()
        if "risk_score" not in view.columns and "anomaly_score" in view.columns:
            view["risk_score"] = pd.to_numeric(view["anomaly_score"], errors="coerce")
        if "risk_score" in view.columns:
            view["risk_score"] = pd.to_numeric(view["risk_score"], errors="coerce").fillna(0)
            view = view[view["risk_score"] >= min_risk].sort_values("risk_score", ascending=False)
        elif "risk_tier" in view.columns:
            order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            view["_ord"] = view["risk_tier"].astype(str).str.upper().map(order).fillna(9)
            view = view.sort_values("_ord").drop(columns=["_ord"])
        show = [
            c
            for c in (
                "mmsi",
                "vessel_name",
                "vessel_type",
                "risk_tier",
                "risk_score",
                "anomaly_score",
                "in_kenya_eez",
                "in_kenya_box",
                "near_port",
                "near_mombasa",
                "mpa_interaction_flag",
                "low_speed_ratio",
                "behaviour_score",
                "behaviour_level",
                "track_efficiency",
                "distance_nm",
                "last_seen",
                "lat",
                "lon",
                "sog",
            )
            if c in view.columns
        ]
        st.dataframe(view[show] if show else view, width="stretch", hide_index=True)

        # distribution
        if "risk_tier" in vessels.columns:
            st.markdown("##### Risk tier mix")
            tier_counts = (
                vessels["risk_tier"].astype(str).str.upper().value_counts().rename_axis("tier").reset_index(name="n")
            )
            st.bar_chart(tier_counts.set_index("tier"))

with tab_beh:
    st.markdown("#### Behaviour score cards")
    if beh.empty:
        st.info("No `fact_vessel_behaviour_scores` rows in window.")
    else:
        b = beh.copy()
        if "risk_score" in b.columns:
            b["risk_score"] = pd.to_numeric(b["risk_score"], errors="coerce").fillna(0)
            b = b[b["risk_score"] >= min_risk].sort_values("risk_score", ascending=False)
        show = [
            c
            for c in (
                "mmsi",
                "vessel_name",
                "vessel_type",
                "risk_score",
                "loitering_score",
                "dark_score",
                "mpa_score",
                "speed_anomaly_score",
                "window_start",
                "window_end",
                "evidence",
                "computed_at",
            )
            if c in b.columns
        ]
        st.dataframe(b[show] if show else b, width="stretch", hide_index=True)
        score_cols = [
            c
            for c in (
                "risk_score",
                "loitering_score",
                "dark_score",
                "mpa_score",
                "speed_anomaly_score",
            )
            if c in b.columns
        ]
        if score_cols and "mmsi" in b.columns:
            top = b.head(15)
            label = top["mmsi"].astype(str)
            if "vessel_name" in top.columns:
                label = top["vessel_name"].fillna(top["mmsi"]).astype(str).str.slice(0, 18)
            chart = top[score_cols].copy()
            chart.index = label.values
            st.bar_chart(chart)

with tab_anom:
    st.markdown("#### Detected anomalies")
    if anom.empty:
        st.info(
            "No anomalies. Optional: `python ingestion/ml_vessel_anomaly.py` "
            "(writes `fact_vessel_anomalies`)."
        )
    else:
        st.dataframe(anom.head(200), width="stretch", hide_index=True)

with tab_geo:
    st.markdown("#### Geofence intelligence")
    c1, c2 = st.columns(2)
    with c1:
        fences = snap.geofences
        if fences is None or fences.empty:
            st.caption("No dim_geofences")
        else:
            st.dataframe(fences, width="stretch", hide_index=True)
    with c2:
        if gf.empty:
            st.caption("No geofence events in window")
        else:
            st.dataframe(gf.head(150), width="stretch", hide_index=True)
            if "fence_name" in gf.columns:
                st.markdown("##### Events by fence")
                st.bar_chart(gf["fence_name"].value_counts())

st.markdown("---")
st.caption(
    "Intelligence layer sits on Phase 12 maritime jobs. "
    "Open **Vessel Tracking** for maps and MMSI track replay."
)
close_page()

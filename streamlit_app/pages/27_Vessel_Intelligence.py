"""Phase 12 — Vessel Intelligence profiles (Kenya)."""

import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

try:
    from db_config import get_db_uri
except ImportError:

    def get_db_uri():
        import os

        return os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL")


st.set_page_config(
    page_title="Vessel Intelligence", page_icon=":material/sailing:", layout="wide"
)

try:
    from ow_theme import apply_theme, init_a11y_defaults

    init_a11y_defaults()
    apply_theme()
except Exception:
    pass

st.title("Vessel Intelligence")
st.caption(
    "Profiles, behaviour, geofences · Kenya EEZ · Human review only — not legal findings"
)


def _sa_uri(uri: str) -> str:
    if not uri:
        return uri
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


DB = get_db_uri()


@st.cache_data(ttl=45)
def load():
    if not DB:
        empty = pd.DataFrame({"error": ["No database URI configured."]})
        return empty, empty, empty

    eng = create_engine(_sa_uri(DB), pool_pre_ping=True)

    def q(sql, params=None):
        try:
            return pd.read_sql(text(sql), eng, params=params or {})
        except Exception as e:  # noqa: BLE001
            return pd.DataFrame({"error": [str(e)]})

    profiles = q(
        """
        SELECT * FROM fact_vessel_profiles
        ORDER BY risk_score DESC NULLS LAST
        """
    )
    fences = q("SELECT * FROM dim_geofences")
    ge = q(
        """
        SELECT * FROM fact_geofence_events
        ORDER BY event_time DESC NULLS LAST
        LIMIT 200
        """
    )
    return profiles, fences, ge


profiles, fences, ge = load()

if profiles is None or profiles.empty or "error" in getattr(profiles, "columns", []):
    err = None
    if profiles is not None and not profiles.empty and "error" in profiles.columns:
        err = profiles.iloc[0].get("error")
    st.warning(
        "No vessel profiles. Run `python ingestion/init_phase12_maritime.py` and "
        "`python ingestion/run_phase12_maritime.py`"
        + (f"\n\n({err})" if err else "")
    )
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Vessels profiled", len(profiles))
c2.metric(
    "Elevated+",
    int((pd.to_numeric(profiles.get("risk_score"), errors="coerce").fillna(0) >= 50).sum()),
)
c3.metric(
    "Near Mombasa",
    int(profiles["near_mombasa"].fillna(False).astype(bool).sum())
    if "near_mombasa" in profiles.columns
    else 0,
)
c4.metric(
    "MPA proxy hits",
    int(profiles["mpa_interaction_flag"].fillna(False).astype(bool).sum())
    if "mpa_interaction_flag" in profiles.columns
    else 0,
)

st.subheader("Fleet risk table")
st.dataframe(
    profiles[
        [
            c
            for c in [
                "vessel_name",
                "mmsi",
                "vessel_type",
                "risk_score",
                "behaviour_level",
                "confidence_score",
                "speed_mean",
                "low_speed_ratio",
                "track_efficiency",
                "near_mombasa",
                "mpa_interaction_flag",
                "geofence_hits",
                "evidence",
            ]
            if c in profiles.columns
        ]
    ],
    use_container_width=True,
    hide_index=True,
)

label_col = "vessel_name" if "vessel_name" in profiles.columns else "mmsi"
names = profiles[label_col].fillna(profiles["mmsi"]).astype(str).tolist()
choice = st.selectbox("Vessel dossier", options=names)
row = profiles[profiles[label_col].fillna(profiles["mmsi"]).astype(str) == choice].iloc[0]

st.subheader(f"Dossier — {choice}")
a, b, c = st.columns(3)
a.metric("Risk", f"{row.get('risk_score', '—')}")
b.metric("Behaviour", str(row.get("behaviour_level")))
c.metric("Confidence", f"{row.get('confidence_score', '—')}")
st.write(
    f"**MMSI:** {row.get('mmsi')} · **Type:** {row.get('vessel_type')} · "
    f"**Last position:** {row.get('last_lat')}, {row.get('last_lon')} · "
    f"**Last seen:** {row.get('last_seen')}"
)
st.write(f"**Evidence:** {row.get('evidence')}")

# Track
track = pd.DataFrame()
if DB:
    try:
        eng = create_engine(_sa_uri(DB), pool_pre_ping=True)
        track = pd.read_sql(
            text(
                """
                SELECT event_time, latitude, longitude, sog
                FROM fact_vessel_track_points
                WHERE mmsi = :m
                ORDER BY event_time
                """
            ),
            eng,
            params={"m": str(row["mmsi"])},
        )
    except Exception:
        track = pd.DataFrame()

if not track.empty:
    st.subheader("Track history")
    fig = px.line(
        track,
        x="longitude",
        y="latitude",
        markers=True,
        hover_data=["event_time", "sog"] if "sog" in track.columns else ["event_time"],
    )
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(track.tail(50), use_container_width=True, hide_index=True)
else:
    st.caption("No track points for this MMSI.")

st.subheader("Geofence events (fleet)")
if ge is not None and not ge.empty and "error" not in ge.columns:
    st.dataframe(ge.head(100), use_container_width=True, hide_index=True)
else:
    st.caption("No geofence events.")

if fences is not None and not fences.empty and "error" not in fences.columns:
    with st.expander("Configured geofences"):
        st.dataframe(fences, use_container_width=True, hide_index=True)

st.info(
    "MPA fence is a demo proxy for engineering tests — not an official protected-area boundary. "
    "Behaviour scores support human review only."
)

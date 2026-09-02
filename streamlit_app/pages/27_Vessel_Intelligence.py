"""Phase 12 — Vessel Intelligence profiles (Kenya)."""

import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Vessel Intelligence", page_icon=":material/sailing:", layout="wide")
st.title("Vessel Intelligence")
st.caption("Profiles, behaviour, geofences · Kenya EEZ · Human review only — not legal findings")

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=45)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql, params=None):
        try:
            return pd.read_sql(text(sql), eng, params=params or {})
        except Exception as e:
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
        ORDER BY event_time DESC LIMIT 200
        """
    )
    return profiles, fences, ge


profiles, fences, ge = load()

if profiles is None or profiles.empty or "error" in getattr(profiles, "columns", []):
    st.warning("No vessel profiles. Run init_phase12_maritime.py and run_phase12_maritime.py")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Vessels profiled", len(profiles))
c2.metric("Elevated+", int((profiles["risk_score"] >= 50).sum()))
c3.metric("Near Mombasa", int(profiles["near_mombasa"].fillna(False).sum()))
c4.metric("MPA proxy hits", int(profiles["mpa_interaction_flag"].fillna(False).sum()))

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
    width="stretch",
)

names = profiles["vessel_name"].fillna(profiles["mmsi"]).tolist()
choice = st.selectbox("Vessel dossier", options=names)
row = profiles[profiles["vessel_name"].fillna(profiles["mmsi"]) == choice].iloc[0]

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
eng = create_engine(DB, pool_pre_ping=True)
try:
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
    fig = px.line(track, x="longitude", y="latitude", markers=True, hover_data=["event_time", "sog"])
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch")
    st.dataframe(track.tail(50), width="stretch")
else:
    st.caption("No track points for this MMSI.")

st.subheader("Geofence events (fleet)")
if ge is not None and not ge.empty and "error" not in ge.columns:
    st.dataframe(ge.head(100), width="stretch")
else:
    st.caption("No geofence events.")

if fences is not None and not fences.empty and "error" not in fences.columns:
    with st.expander("Configured geofences"):
        st.dataframe(fences, width="stretch")

st.info(
    "MPA fence is a demo proxy for engineering tests — not an official protected-area boundary. "
    "Behaviour scores support human review only."
)
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine

st.set_page_config(page_title="Port Intelligence", page_icon="⚓", layout="wide")
st.title("⚓ Mombasa Port Intelligence")

@st.cache_data(ttl=120)
def load_port_metrics():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    try:
        metrics = pd.read_sql("SELECT * FROM fact_port_metrics ORDER BY metric_date DESC LIMIT 1", engine)
        activity = pd.read_sql("SELECT * FROM port_activity ORDER BY event_time DESC", engine)
        return metrics, activity
    except Exception as e:
        st.error(str(e))
        return pd.DataFrame(), pd.DataFrame()

metrics, activity = load_port_metrics()

if metrics.empty:
    st.warning("No port metrics yet. Run the operational intelligence engine.")
else:
    m = metrics.iloc[0]

    st.subheader("MOMBASA PORT INTELLIGENCE")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active vessels", int(m["active_vessels"]))
    c2.metric("Arrivals (7d)", int(m["arrivals"]))
    c3.metric("Departures (7d)", int(m["departures"]))
    c4.metric("Port congestion", m["congestion_level"])

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Avg. waiting time", f"{m['avg_waiting_hours']} hrs")
    c6.metric("Container vessels", int(m["container_vessels"]))
    c7.metric("Tankers", int(m["tankers"]))
    c8.metric("Fishing vessels", int(m["fishing_vessels"]))

    st.metric("vs 30-day baseline", f"{m['vs_30d_baseline_pct']:+.1f}%")

    if m["congestion_level"] == "HIGH":
        st.error(f"⚠ Vessel activity {m['vs_30d_baseline_pct']:+.1f}% above 30-day baseline — congestion HIGH")
    elif m["congestion_level"] == "MODERATE":
        st.warning("Port congestion is MODERATE")
    else:
        st.success("Port congestion is LOW")

    if not activity.empty:
        activity["event_time"] = pd.to_datetime(activity["event_time"])
        st.subheader("Vessel Type Mix (recent)")
        type_counts = activity["vessel_type"].value_counts().reset_index()
        type_counts.columns = ["vessel_type", "count"]
        fig = px.pie(type_counts, names="vessel_type", values="count", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Recent Events")
        st.dataframe(
            activity[["event_time", "event_type", "vessel_name", "vessel_type", "flag_country", "status"]].head(25),
            use_container_width=True
        )
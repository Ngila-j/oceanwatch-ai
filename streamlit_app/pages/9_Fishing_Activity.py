import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine
from datetime import datetime, timedelta

st.set_page_config(page_title="Fishing Activity", page_icon="🐟", layout="wide")
st.title("🐟 Fishing Activity Intelligence")
st.caption("Estimated fishing effort and vessel activity within the Kenya EEZ / Western Indian Ocean monitoring area")

@st.cache_data(ttl=300)
def load_fishing_data():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    try:
        df = pd.read_sql("""
            SELECT *
            FROM fishing_activity
            ORDER BY event_time DESC
        """, engine)
        return df
    except Exception as e:
        st.error(f"Could not load fishing data: {e}")
        return pd.DataFrame()

df = load_fishing_data()

if df.empty:
    st.warning("No fishing activity data found. Run the seed script first.")
    st.code("docker exec -it oceanwatch_airflow_web python /opt/airflow/ingestion/seed_fishing_activity.py")
else:
    df["event_time"] = pd.to_datetime(df["event_time"])
    df["date"] = df["event_time"].dt.date

    last_7d = df[df["event_time"] >= datetime.utcnow() - timedelta(days=7)]
    last_24h = df[df["event_time"] >= datetime.utcnow() - timedelta(hours=24)]

    # ===== KPIs =====
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Events (7 days)", len(last_7d))
    with col2:
        st.metric("Total Fishing Hours (7d)", f"{last_7d['fishing_hours'].sum():.0f}")
    with col3:
        st.metric("Events (last 24h)", len(last_24h))
    with col4:
        high_effort = len(last_7d[last_7d["apparent_effort"] == "HIGH"])
        st.metric("High Effort Events (7d)", high_effort)

    st.divider()

    # ===== Map =====
    st.subheader("Fishing Event Locations (sample)")
    m = folium.Map(location=[-1.5, 42.0], zoom_start=6, tiles="CartoDB positron")

    # Monitoring box
    folium.Rectangle(
        bounds=[[-5.0, 39.0], [2.0, 45.0]],
        color="blue",
        fill=True,
        fill_opacity=0.08,
        popup="Monitoring Area"
    ).add_to(m)

    # Plot recent points
    for _, row in last_7d.head(80).iterrows():
        color = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}.get(row["apparent_effort"], "blue")
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=4,
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=f"{row['vessel_name']}<br>{row['vessel_type']}<br>{row['apparent_effort']}"
        ).add_to(m)

    st_folium(m, width=None, height=450, returned_objects=[])

    st.caption("Green = Low effort · Orange = Medium · Red = High effort")

    # ===== Charts =====
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Vessel Type Distribution (7 days)")
        type_counts = last_7d["vessel_type"].value_counts().reset_index()
        type_counts.columns = ["vessel_type", "count"]
        fig = px.pie(type_counts, names="vessel_type", values="count", hole=0.35)
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("Effort Level (7 days)")
        effort_counts = last_7d["apparent_effort"].value_counts().reset_index()
        effort_counts.columns = ["apparent_effort", "count"]
        fig = px.bar(effort_counts, x="apparent_effort", y="count", color="apparent_effort")
        st.plotly_chart(fig, use_container_width=True)

    # Daily trend
    st.subheader("Daily Fishing Events")
    daily = last_7d.groupby("date").size().reset_index(name="events")
    fig_daily = px.line(daily, x="date", y="events", markers=True)
    st.plotly_chart(fig_daily, use_container_width=True)

    # Table
    st.subheader("Recent Fishing Events")
    st.dataframe(
        df[["event_time", "vessel_name", "vessel_type", "flag_country",
            "latitude", "longitude", "fishing_hours", "apparent_effort"]]
        .head(40),
        use_container_width=True
    )

    st.info("Currently using realistic sample data. This structure is ready for Global Fishing Watch and AIS integration.")
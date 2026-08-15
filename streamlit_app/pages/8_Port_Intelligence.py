import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine
from datetime import datetime, timedelta

st.set_page_config(page_title="Port Intelligence", page_icon="⚓", layout="wide")
st.title("⚓ Mombasa Port Intelligence")
st.caption("Operational overview of vessel activity at Mombasa Port")

@st.cache_data(ttl=300)
def load_port_data():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    try:
        df = pd.read_sql("""
            SELECT *
            FROM port_activity
            ORDER BY event_time DESC
        """, engine)
        return df
    except Exception as e:
        st.error(f"Could not load port data: {e}")
        return pd.DataFrame()

df = load_port_data()

if df.empty:
    st.warning("No port activity data found. Run the seed script first.")
    st.code("docker exec -it oceanwatch_airflow_web python /opt/airflow/ingestion/seed_port_activity.py")
else:
    # Convert time
    df["event_time"] = pd.to_datetime(df["event_time"])
    df["date"] = df["event_time"].dt.date

    # ===== KPI Row =====
    last_24h = df[df["event_time"] >= datetime.utcnow() - timedelta(hours=24)]
    last_7d = df[df["event_time"] >= datetime.utcnow() - timedelta(days=7)]

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Arrivals (7 days)", len(last_7d[last_7d["event_type"] == "ARRIVAL"]))

    with col2:
        st.metric("Departures (7 days)", len(last_7d[last_7d["event_type"] == "DEPARTURE"]))

    with col3:
        st.metric("Events (last 24h)", len(last_24h))

    with col4:
        in_port = len(df[df["status"] == "IN_PORT"])
        st.metric("Currently marked In Port", in_port)

    st.divider()

    # ===== Charts =====
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Vessel Type Mix (7 days)")
        type_counts = last_7d["vessel_type"].value_counts().reset_index()
        type_counts.columns = ["vessel_type", "count"]
        fig_type = px.pie(type_counts, names="vessel_type", values="count", hole=0.4)
        st.plotly_chart(fig_type, use_container_width=True)

    with col_right:
        st.subheader("Daily Activity Trend")
        daily = last_7d.groupby(["date", "event_type"]).size().reset_index(name="count")
        fig_daily = px.bar(daily, x="date", y="count", color="event_type", barmode="group")
        st.plotly_chart(fig_daily, use_container_width=True)

    # ===== Flag countries =====
    st.subheader("Top Flag Countries (7 days)")
    flag_counts = last_7d["flag_country"].value_counts().head(8).reset_index()
    flag_counts.columns = ["flag_country", "count"]
    fig_flags = px.bar(flag_counts, x="flag_country", y="count", text="count")
    st.plotly_chart(fig_flags, use_container_width=True)

    # ===== Recent activity table =====
    st.subheader("Recent Vessel Events")
    st.dataframe(
        df[["event_time", "event_type", "vessel_name", "vessel_type", "flag_country", "draft_m", "status"]]
        .head(30),
        use_container_width=True
    )

    st.info("This is currently driven by realistic sample data. In the next iteration we will replace it with real AIS feeds.")
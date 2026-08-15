import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine

st.set_page_config(page_title="Fishing Activity", page_icon="🐟", layout="wide")
st.title("🐟 Fishing & Vessel Anomaly Intelligence")
st.caption("Isolation Forest behavioural scores — potential anomalies require human review")

@st.cache_data(ttl=120)
def load_data():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    try:
        anom = pd.read_sql("""
            SELECT * FROM fact_vessel_anomalies
            ORDER BY risk_score DESC
        """, engine)
        ais = pd.read_sql("""
            SELECT DISTINCT ON (mmsi) *
            FROM fact_ais_positions
            ORDER BY mmsi, event_time DESC
        """, engine)
        return anom, ais
    except Exception as e:
        st.error(str(e))
        return pd.DataFrame(), pd.DataFrame()

anom, ais = load_data()

if anom.empty:
    st.warning("No anomaly results. Run: python /opt/airflow/ingestion/ml_vessel_anomaly.py")
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("Vessels scored", len(anom))
    c2.metric("High risk (≥65)", len(anom[anom["risk_score"] >= 65]))
    c3.metric("Model", anom.iloc[0]["model_name"] if "model_name" in anom.columns else "isolation_forest_v1")

    st.subheader("Elevated Behavioural Risk")
    for _, row in anom[anom["risk_score"] >= 60].head(12).iterrows():
        st.warning(
            f"**{row['vessel_name']}** ({row['vessel_type']})  |  "
            f"Risk **{row['risk_score']}/100**  |  Confidence {row['confidence_score']}  |  {row['status']}"
        )
        st.caption(f"Evidence: {row['evidence']}")
        st.caption(f"Location: {row['latitude']:.3f}, {row['longitude']:.3f}  |  Flag: {row['flag_country']}")
        st.divider()

    st.subheader("Vessel Map (latest positions)")
    m = folium.Map(location=[-1.5, 42.0], zoom_start=6, tiles="CartoDB positron")
    folium.Rectangle(bounds=[[-5, 39], [2, 45]], color="blue", fill=True, fill_opacity=0.08).add_to(m)

    risk_map = dict(zip(anom["mmsi"], anom["risk_score"])) if not anom.empty else {}
    for _, row in ais.iterrows():
        r = risk_map.get(row["mmsi"], 0)
        color = "red" if r >= 75 else "orange" if r >= 60 else "green"
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=5, color=color, fill=True, fill_opacity=0.8,
            popup=f"{row['vessel_name']}<br>Risk: {r}"
        ).add_to(m)

    st_folium(m, width=None, height=450, returned_objects=[])
    st.caption("Red = high risk · Orange = elevated · Green = lower risk")

    st.subheader("Full scores")
    st.dataframe(
        anom[["vessel_name", "vessel_type", "flag_country", "risk_score",
              "confidence_score", "status", "evidence"]],
        use_container_width=True
    )
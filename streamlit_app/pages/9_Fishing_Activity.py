import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine

st.set_page_config(page_title="Fishing Activity", page_icon="🐟", layout="wide")
st.title("🐟 Fishing Activity Intelligence")
st.caption("Potential anomalous fishing behaviour — requires human review")

@st.cache_data(ttl=120)
def load_data():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    try:
        risk = pd.read_sql("SELECT * FROM fact_fishing_risk ORDER BY risk_score DESC", engine)
        activity = pd.read_sql("SELECT * FROM fishing_activity ORDER BY event_time DESC LIMIT 200", engine)
        return risk, activity
    except Exception as e:
        st.error(str(e))
        return pd.DataFrame(), pd.DataFrame()

risk, activity = load_data()

if risk.empty and activity.empty:
    st.warning("No fishing data. Run the operational intelligence engine.")
else:
    if not risk.empty:
        st.subheader("Elevated Fishing-Risk Events")
        for _, row in risk.head(10).iterrows():
            st.warning(
                f"**{row['vessel_name']}**  |  Risk Score: **{row['risk_score']}/100**  |  "
                f"Confidence: {row['confidence_score']}  |  Status: {row['status']}"
            )
            st.caption(f"Evidence: {row['evidence']}")
            st.caption(f"Location: {row['latitude']:.3f}, {row['longitude']:.3f}  |  {row['vessel_type']}  |  {row['flag_country']}")
            st.divider()

    if not activity.empty:
        st.subheader("Fishing Event Map (sample)")
        m = folium.Map(location=[-1.5, 42.0], zoom_start=6, tiles="CartoDB positron")
        folium.Rectangle(bounds=[[-5, 39], [2, 45]], color="blue", fill=True, fill_opacity=0.08).add_to(m)

        for _, row in activity.head(60).iterrows():
            color = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}.get(row.get("apparent_effort", "LOW"), "blue")
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]],
                radius=4, color=color, fill=True, fill_opacity=0.7,
                popup=row.get("vessel_name", "")
            ).add_to(m)

        st_folium(m, width=None, height=420, returned_objects=[])
        st.caption("Green = Low · Orange = Medium · Red = High apparent effort")
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

st.set_page_config(page_title="Habitat Suitability", page_icon="🪸", layout="wide")
st.title("🪸 Predicted Habitat Suitability")
st.caption("Based on available SST and chlorophyll features — not a prediction of where fish are")

@st.cache_data(ttl=120)
def load():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    return pd.read_sql("SELECT * FROM fact_habitat_suitability ORDER BY as_of_date DESC LIMIT 10", engine)

df = load()

if df.empty:
    st.warning("No habitat data. Run ml_habitat_suitability.py")
else:
    r = df.iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Suitability Score", f"{r['suitability_score']:.1f}")
    c2.metric("Class", r["suitability_class"])
    c3.metric("SST / CHL", f"{r['sst_celsius']:.2f}°C / {r['chlorophyll_mg_m3']:.3f}")

    if r["suitability_class"] == "HIGH":
        st.success(r["notes"])
    elif r["suitability_class"] == "MEDIUM":
        st.info(r["notes"])
    else:
        st.warning(r["notes"])

    st.subheader("History")
    st.dataframe(df, use_container_width=True)
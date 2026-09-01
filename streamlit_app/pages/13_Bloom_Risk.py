import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

st.set_page_config(page_title="Bloom Risk", page_icon="ðŸŒŠ", layout="wide")
st.title("Chlorophyll Bloom-Risk Probability")
st.caption("Bloom-risk indicator â€” not a confirmed harmful algal bloom diagnosis")

@st.cache_data(ttl=120)
def load():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    return pd.read_sql("SELECT * FROM fact_bloom_risk ORDER BY risk_date DESC LIMIT 10", engine)

df = load()

if df.empty:
    st.warning("No bloom risk data. Run ml_bloom_probability.py")
else:
    r = df.iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Bloom Probability", f"{r['bloom_probability']:.1f}%")
    c2.metric("Risk Level", r["risk_level"])
    c3.metric("CHL Anomaly", f"{r['chl_anomaly_pct']:+.1f}%")

    if r["risk_level"] == "ELEVATED":
        st.warning(f"**Elevated bloom-risk** â€” {r['drivers']}")
    elif r["risk_level"] == "WATCH":
        st.info(f"**Watch** â€” {r['drivers']}")
    else:
        st.success(f"**Low bloom-risk** â€” {r['drivers']}")

    st.subheader("Detail")
    st.dataframe(df, width="stretch")
    st.caption("Confirmation of harmful blooms requires additional biological sampling.")

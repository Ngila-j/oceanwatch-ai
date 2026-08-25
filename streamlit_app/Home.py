import streamlit as st

from components.branding import attribution_footer, bandwidth_toggle
from components.data_access import load_status_strip

st.set_page_config(page_title="OceanWatch AI", page_icon="🌊", layout="wide")
bandwidth_toggle()

st.title("🌊 OceanWatch AI")
st.subheader("Western Indian Ocean · Kenya EEZ — free open intelligence")

status = load_status_strip()
s1, s2, s3, s4, s5 = st.columns(5)
s1.metric("Ocean data", str(status.get("ocean") or "—"))
s2.metric("Port metrics", str(status.get("port") or "—"))
s3.metric("WIO-OII", str(status.get("wio") or "—"))
s4.metric("Quality run", str(status.get("quality") or "—"))
s5.metric("Alerts stored", str(status.get("alerts_n") or 0))

st.markdown(
    """
**Start here:** sidebar → **Kenya EEZ Today**

### Who this is for
- Port & logistics awareness (Mombasa)
- Fisheries / coastal conditions context
- Maritime exploratory awareness
- Environment & research

### Free access principles
- Open and registered open-data services where possible
- Clear attribution and methodology
- Decision-support only — not legal advice
"""
)

st.info(
    "Path: **Kenya EEZ Today** → **WIO Intelligence Index** → **System Health** → **Methodology & Sources**"
)

st.markdown("### Partner API (local)")
st.code(
    """# Health
curl http://localhost:8000/health

# WIO index
curl http://localhost:8000/v1/wio/index

# Ocean conditions
curl "http://localhost:8000/v1/ocean/conditions?limit=5"

# Interactive docs
# http://localhost:8000/docs
""",
    language="bash",
)

attribution_footer()
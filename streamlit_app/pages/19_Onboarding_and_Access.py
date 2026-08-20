import streamlit as st

st.set_page_config(page_title="Onboarding & Access", page_icon="📘", layout="wide")
st.title("📘 Onboarding, Access & Monetization Framing")

st.markdown(
    """
### What OceanWatch is
Kenya-first **Western Indian Ocean** intelligence: ocean conditions, port risk,
fishing effort (GFW), vessel activity, ML forecasts/anomalies, and the **WIO-OII** index.

### Who it serves

| Segment | Primary value |
|---------|----------------|
| Port operators | Congestion, risk, waiting time |
| Fisheries / BMU | Effort, conditions, habitat |
| Coast Guard / Navy | MDA, potential anomalies |
| NEMA / environment | SST, bloom, climate indicators |
| Researchers | API + CSV explorer |

### Access tiers (product model)
1. **Public** — high-level ocean summaries
2. **Research** — API + forecasts + GFW attribution
3. **Agency SaaS** — full ops dashboards + alerts
4. **Custom** — early-warning + dedicated reports

Identity, billing, and WhatsApp delivery are future hardening — not claimed as production-ready.

### Reports
- **Weekly Ocean Brief** PDF from `generate_weekly_brief.py`
- Output: `reports/` (host) or `/opt/airflow/data/reports` (Docker)

### Low-bandwidth / field use
- Prefer Executive Summary + WIO-OII pages
- Avoid heavy maps on slow links
- PDF brief for offline sharing

### API
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

### Data ethics
- Vessel anomaly is **not** a determination of illegality
- GFW: non-commercial license + attribution
- Partner data only with authorized access

### Out of scope (roadmap, not code)
- Real multi-tenant SaaS billing
- Production WhatsApp / SMTP at scale
- Formal institutional data-sharing agreements (KMD, KMFRI, etc.)
"""
)
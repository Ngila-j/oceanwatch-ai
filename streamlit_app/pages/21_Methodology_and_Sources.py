import streamlit as st

from components.branding import attribution_footer

st.set_page_config(page_title="Methodology & Sources", page_icon="📎", layout="wide")
st.title("📎 Methodology & Sources")
st.caption("Transparency for a free, open Western Indian Ocean intelligence prototype.")

st.markdown(
    """
## Purpose

OceanWatch AI combines open ocean, vessel, and fishing-effort related datasets focused on
**Kenya’s EEZ and Mombasa** to provide **decision-support indicators** — not official
government statistics and not legal determinations.

## Data sources

| Source | What we use | Notes |
|--------|-------------|--------|
| NOAA CO-OPS | Tide / water level samples | Open API; verify terms for your deployment |
| Copernicus Marine | SST, chlorophyll summaries | Account required; follow CMEMS licence |
| Global Fishing Watch | Fishing effort aggregates | **Attribution required**; many free tiers are **non-commercial** |
| AIS (sample / live) | Positions for analytics demos | Live coverage can be sparse; sample data is labelled in DB `source` |

## Derived intelligence

### WIO-OII (Western Indian Ocean Ocean Intelligence Index)
- Scale: **0–100** (prototype)
- Components (v0.2 weights): Ocean Health 25%, Maritime Activity 20%,
  Fishing Pressure 20%, Port (inverse risk) 20%, Environmental (inverse risk) 15%
- Includes **confidence_score** and free-text **drivers**
- **Not** an official regional index

### Port risk / congestion
- Built from port activity metrics and related features
- May include seeded or modelled activity for pipeline continuity — always check freshness

### SST forecast
- Short-horizon forecast from recent daily SST
- Simple baselines (e.g. persistence / regularized lag models); see `ml_model_metrics`

### Vessel anomaly scores
- Unsupervised / heuristic behaviour scores
- **Potential anomaly only — not proof of illegal activity**

### Bloom / habitat scores
- Indicator-style outputs from ocean features
- Interpret with local ecological expertise

### Data quality scores
- Completeness, validity, timeliness, consistency → overall score per dataset
- Shown on **System Health** and **Kenya EEZ Today**

## Limitations

- Spatial focus is intentionally **Kenya-first**, not global
- Satellite and AIS feeds have gaps, latency, and cloud/coverage limits
- Free prototype: no formal SLA
- Licence compliance is the **user’s responsibility** for any redistribution

## How to cite (suggested)

OceanWatch AI (year). Kenya EEZ / Mombasa open intelligence dashboard.
https://github.com/Ngila-j/oceanwatch-ai

Include third-party attribution (especially Global Fishing Watch) when publishing results.
"""
)

attribution_footer()
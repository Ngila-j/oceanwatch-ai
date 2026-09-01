import streamlit as st

from components.branding import attribution_footer, bandwidth_toggle

st.set_page_config(page_title="API Access", page_icon="🔌", layout="wide")
bandwidth_toggle()

st.title("Partner API  free access (prototype)")
st.caption(
    "Copernicus-style open access: explore the API freely in development. "
    "Hosted free-key issuance can be added when the server is public."
)

st.markdown(
    """
## Base URL (local)

`http://localhost:8000`

## Interactive docs

[http://localhost:8000/docs](http://localhost:8000/docs)

## Free-tier policy (intended)

| Tier | Access | Limits |
|------|--------|--------|
| Public | Health, summaries | Rate limited when hosted |
| Research free | Forecasts, WIO index, conditions | Non-commercial; attribution |
| Future commercial | Higher limits / licensed layers | After commercial data keys |

**Today:** no API key required on local Docker.  
**Later (hosted):** keys like `ow_free_xxxx` with daily quotas.

## Examples
"""
)

st.code(
    """curl -s http://localhost:8000/health
curl -s http://localhost:8000/v1/wio/index
curl -s "http://localhost:8000/v1/ocean/conditions?limit=5"
curl -s http://localhost:8000/v1/forecasts/sst
curl -s http://localhost:8000/v1/gfw/effort/summary
""",
    language="bash",
)

st.code(
    """import requests
r = requests.get("http://localhost:8000/v1/wio/index", timeout=30)
print(r.json())
""",
    language="python",
)

st.markdown(
    """
## Free API key stub (design)

When you host publicly, store keys in a table such as:

- `api_keys(key_id, key_hash, tier, daily_quota, created_at, active)`
- Client sends header: `X-API-Key: ow_free_...`
- Middleware checks quota; public docs stay available

Until then, use local API without keys and document licence limits (especially GFW).
"""
)

st.warning(
    "Do not expose an open API to the internet without rate limits and HTTPS."
)
attribution_footer()

# OceanWatch AI

**Western Indian Ocean / Kenya EEZ Monitoring Platform**

OceanWatch AI ingests, transforms, and visualises ocean and maritime intelligence focused on Kenya’s Exclusive Economic Zone and Mombasa port — with a clear path to regional expansion (Tanzania, Seychelles, northern Mozambique Channel).

## Architecture

```text
NOAA + Copernicus + GFW + AIS
        ↓
  Apache Airflow (orchestration)
        ↓
  DuckDB staging → dbt → PostgreSQL/PostGIS
        ↓
  Operational intelligence + ML (SST, anomalies, port/bloom/habitat)
        ↓
  WIO-OII index → Weekly Ocean Brief PDF
        ↓
  Streamlit (multi-persona) + FastAPI partner API


### New ops features
- **Command Center** — fused multi-domain posture, attention queue, domain finder
- **Mission context** — shared region / lookback / severity across pages
- **Watchlist + Operator Notebook** — pin vessels/ports and session notes; export mission packs
- **API** — `GET /v1/situation`, `GET /v1/coverage/countries`


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
# Oceanwatch AI

Western Indian Ocean / Kenya EEZ Monitoring Platform

End-to-end platform that ingests, transforms and visualises ocean conditions (SST, Chlorophyll-a, tides) focused on the Kenyan EEZ and Mombasa region.

## Architecture
- Ingestion: NOAA Tides + Copernicus Marine
- Orchestration: Apache Airflow
- Storage: PostgreSQL + PostGIS
- Transformation: DuckDB + dbt (star schema)
- Visualisation: Multi-page Streamlit dashboard

## Quick Start

1. Start services
   docker compose up -d

2. Airflow UI → http://localhost:8080 (admin / admin)

3. Create ingestion/.env with your Copernicus credentials

4. Trigger the oceanwatch_full_pipeline DAG

5. Launch dashboard
   cd streamlit_app
   python -m streamlit run Home.py

## Main Components
- dags/                  Airflow DAGs
- ingestion/             Data ingestion scripts
- oceanwatch_transformations/   dbt models
- streamlit_app/         Dashboard

## Data Model
- dim_date, dim_location
- fact_ocean_conditions (SST + CHL + tides)
- stg_tides, raw_* tables

## License
MIT

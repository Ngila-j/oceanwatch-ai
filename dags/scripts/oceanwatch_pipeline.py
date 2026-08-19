from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "oceanwatch",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="oceanwatch_full_pipeline",
    default_args=default_args,
    description="OceanWatch: Ingest → dbt → Ops → ML → GFW/AIS → WIO-OII → Weekly Brief",
    schedule_interval="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["oceanwatch", "ml", "gfw", "ais", "wio-oii", "reports"],
) as dag:

    fetch_noaa = BashOperator(
        task_id="fetch_ocean_data",
        bash_command="python /opt/airflow/ingestion/fetch_ocean_data.py",
    )

    fetch_copernicus = BashOperator(
        task_id="fetch_copernicus_data",
        bash_command="python /opt/airflow/ingestion/fetch_copernicus_ocean.py",
    )

    stage_with_duckdb = BashOperator(
        task_id="stage_with_duckdb",
        bash_command="python /opt/airflow/ingestion/stage_tides_duckdb.py",
    )

    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=(
            "cd /opt/airflow/oceanwatch_transformations && "
            "dbt deps --profiles-dir /opt/airflow/oceanwatch_transformations"
        ),
    )

    run_dbt = BashOperator(
        task_id="run_dbt_models",
        bash_command=(
            "cd /opt/airflow/oceanwatch_transformations && "
            "dbt run --profiles-dir /opt/airflow/oceanwatch_transformations"
        ),
    )

    test_dbt = BashOperator(
        task_id="test_dbt_models",
        bash_command=(
            "cd /opt/airflow/oceanwatch_transformations && "
            "dbt test --profiles-dir /opt/airflow/oceanwatch_transformations"
        ),
    )

    init_schema = BashOperator(
        task_id="init_operational_schema",
        bash_command="python /opt/airflow/ingestion/init_operational_schema.py",
    )

    seed_port = BashOperator(
        task_id="seed_port_activity",
        bash_command="python /opt/airflow/ingestion/seed_port_activity.py",
    )

    seed_fishing = BashOperator(
        task_id="seed_fishing_activity",
        bash_command="python /opt/airflow/ingestion/seed_fishing_activity.py",
    )

    seed_ais = BashOperator(
        task_id="seed_ais_sample",
        bash_command="python /opt/airflow/ingestion/seed_ais_sample.py",
    )

    fetch_ais_live = BashOperator(
        task_id="fetch_ais_live",
        bash_command=(
            "AIS_COLLECT_SECONDS=120 AIS_MAX_RAW=8000 "
            "python /opt/airflow/ingestion/fetch_ais_realtime.py"
        ),
    )

    fetch_gfw = BashOperator(
        task_id="fetch_gfw_fishing_effort",
        bash_command="python /opt/airflow/ingestion/fetch_gfw_fishing_effort.py",
    )

    run_intelligence = BashOperator(
        task_id="run_operational_intelligence",
        bash_command="python /opt/airflow/ingestion/run_operational_intelligence.py",
    )

    ml_sst = BashOperator(
        task_id="ml_sst_forecast",
        bash_command="python /opt/airflow/ingestion/ml_sst_forecast.py",
    )

    ml_vessel = BashOperator(
        task_id="ml_vessel_anomaly",
        bash_command="python /opt/airflow/ingestion/ml_vessel_anomaly.py",
    )

    ml_port_risk = BashOperator(
        task_id="ml_port_risk",
        bash_command="python /opt/airflow/ingestion/ml_port_risk.py",
    )

    ml_bloom = BashOperator(
        task_id="ml_bloom_probability",
        bash_command="python /opt/airflow/ingestion/ml_bloom_probability.py",
    )

    ml_habitat = BashOperator(
        task_id="ml_habitat_suitability",
        bash_command="python /opt/airflow/ingestion/ml_habitat_suitability.py",
    )

    # Phase 9 — WIO Ocean Intelligence Index
    compute_wio_index = BashOperator(
        task_id="compute_wio_index",
        bash_command="python /opt/airflow/ingestion/compute_wio_index.py",
    )

    # Phase 10 — Weekly Ocean Brief PDF
    weekly_brief = BashOperator(
        task_id="generate_weekly_brief",
        bash_command="python /opt/airflow/ingestion/generate_weekly_brief.py",
    )

    # --- Core ELT ---
    [fetch_noaa, fetch_copernicus] >> stage_with_duckdb >> dbt_deps >> run_dbt >> test_dbt

    # --- Ops seeds / live feeds ---
    run_dbt >> init_schema >> [seed_port, seed_fishing, seed_ais] >> fetch_ais_live
    run_dbt >> fetch_gfw

    [fetch_ais_live, fetch_gfw, seed_fishing] >> run_intelligence

    # --- ML ---
    run_dbt >> ml_sst
    [seed_ais, fetch_ais_live] >> ml_vessel
    run_intelligence >> [ml_port_risk, ml_bloom, ml_habitat]

    # --- WIO-OII after intelligence inputs ---
    [
        test_dbt,
        ml_sst,
        ml_vessel,
        ml_port_risk,
        ml_bloom,
        ml_habitat,
        fetch_gfw,
        run_intelligence,
    ] >> compute_wio_index

    # --- Weekly brief after index ---
    compute_wio_index >> weekly_brief
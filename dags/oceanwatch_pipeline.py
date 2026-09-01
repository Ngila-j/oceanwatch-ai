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
    description="OceanWatch: Ingest → dbt → Ops → ML → GFW/AIS → Alerts → WIO-OII → Digest",
    schedule_interval="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["oceanwatch", "ml", "gfw", "ais"],
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
        task_id="fetch_ais_realtime",
        bash_command="python /opt/airflow/ingestion/fetch_ais_realtime.py",
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
    compute_anomalies = BashOperator(
        task_id="compute_anomalies",
        bash_command="python /opt/airflow/ingestion/compute_anomalies.py",
    )
    generate_alerts = BashOperator(
        task_id="generate_alerts",
        bash_command="python /opt/airflow/ingestion/generate_alerts.py",
    )
    enrich_alerts = BashOperator(
        task_id="enrich_alerts",
        bash_command="python /opt/airflow/ingestion/enrich_alerts.py",
    )
    compute_wio = BashOperator(
        task_id="compute_wio_index",
        bash_command="python /opt/airflow/ingestion/compute_wio_index.py",
    )
    deliver_alerts = BashOperator(
        task_id="deliver_alerts",
        bash_command="python /opt/airflow/ingestion/deliver_alerts.py",
    )

    [fetch_noaa, fetch_copernicus] >> stage_with_duckdb >> dbt_deps >> run_dbt >> test_dbt
    run_dbt >> init_schema >> [seed_port, seed_fishing, seed_ais] >> fetch_ais_live
    run_dbt >> fetch_gfw
    [fetch_ais_live, fetch_gfw, seed_fishing] >> run_intelligence
    run_dbt >> ml_sst
    [seed_ais, fetch_ais_live] >> ml_vessel
    run_intelligence >> [ml_port_risk, ml_bloom, ml_habitat]
    [run_intelligence, ml_vessel, fetch_gfw] >> compute_anomalies
    compute_anomalies >> generate_alerts >> enrich_alerts
    [enrich_alerts, ml_port_risk, ml_bloom, ml_habitat, ml_sst] >> compute_wio
    [enrich_alerts, compute_wio] >> deliver_alerts
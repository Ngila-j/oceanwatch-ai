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
    description="OceanWatch: Ingest → Transform → Operational Intelligence → ML",
    schedule_interval="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["oceanwatch", "ingestion", "dbt", "ml", "alerts"],
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
        bash_command="cd /opt/airflow/oceanwatch_transformations && dbt deps --profiles-dir /opt/airflow/oceanwatch_transformations",
    )

    run_dbt = BashOperator(
        task_id="run_dbt_models",
        bash_command="cd /opt/airflow/oceanwatch_transformations && dbt run --profiles-dir /opt/airflow/oceanwatch_transformations",
    )

    test_dbt = BashOperator(
        task_id="test_dbt_models",
        bash_command="cd /opt/airflow/oceanwatch_transformations && dbt test --profiles-dir /opt/airflow/oceanwatch_transformations",
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

    run_intelligence = BashOperator(
        task_id="run_operational_intelligence",
        bash_command="python /opt/airflow/ingestion/run_operational_intelligence.py",
    )

    ml_sst_forecast = BashOperator(
        task_id="ml_sst_forecast",
        bash_command="python /opt/airflow/ingestion/ml_sst_forecast.py",
    )

    ml_vessel_anomaly = BashOperator(
        task_id="ml_vessel_anomaly",
        bash_command="python /opt/airflow/ingestion/ml_vessel_anomaly.py",
    )

    [fetch_noaa, fetch_copernicus] >> stage_with_duckdb >> dbt_deps >> run_dbt >> test_dbt
    run_dbt >> init_schema >> [seed_port, seed_fishing, seed_ais] >> run_intelligence
    run_dbt >> ml_sst_forecast
    seed_ais >> ml_vessel_anomaly
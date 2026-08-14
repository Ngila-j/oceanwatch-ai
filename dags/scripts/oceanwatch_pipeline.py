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
    description="Oceanwatch pipeline: Ingest → Transform → Alerts",
    schedule_interval="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["oceanwatch", "ingestion", "dbt", "alerts"],
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

    generate_alerts = BashOperator(
        task_id="generate_operational_alerts",
        bash_command="python /opt/airflow/ingestion/generate_alerts.py",
    )

    [fetch_noaa, fetch_copernicus] >> stage_with_duckdb >> dbt_deps >> run_dbt >> test_dbt >> generate_alerts
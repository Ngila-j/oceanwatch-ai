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
    description="Oceanwatch daily pipeline: Ingest → DuckDB staging → dbt",
    schedule_interval="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["oceanwatch", "ingestion", "dbt"],
) as dag:

    fetch_ocean_data = BashOperator(
        task_id="fetch_ocean_data",
        bash_command="python /opt/airflow/ingestion/fetch_ocean_data.py",
    )

    stage_with_duckdb = BashOperator(
        task_id="stage_with_duckdb",
        bash_command="echo 'DuckDB staging placeholder – will be implemented next'",
    )

    run_dbt = BashOperator(
        task_id="run_dbt_models",
        bash_command="cd /opt/airflow/oceanwatch_transformations && dbt run --profiles-dir /opt/airflow/oceanwatch_transformations",
    )

    fetch_ocean_data >> stage_with_duckdb >> run_dbt
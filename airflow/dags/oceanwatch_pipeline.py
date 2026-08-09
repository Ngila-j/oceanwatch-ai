from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    'owner': 'oceanwatch',
    'depends_on_past': False,
    'email_on_failure': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'oceanwatch_daily_pipeline',
    default_args=default_args,
    description='Automated NOAA data ingestion and dbt transformation pipeline',
    schedule_interval='@daily',
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:

    run_ingestion = BashOperator(
        task_id='fetch_and_store_ocean_data',
        bash_command='python /opt/airflow/ingestion/fetch_ocean_data.py',
    )

    run_dbt_transformations = BashOperator(
        task_id='run_dbt_models',
        bash_command='cd /opt/airflow/oceanwatch_transformations && dbt run',
    )

    run_ingestion >> run_dbt_transformations

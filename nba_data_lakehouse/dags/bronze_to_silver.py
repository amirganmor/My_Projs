"""
DAG: bronze_to_silver
======================
Transform Bronze tables into Silver conformed dimensions and facts.
Runs entity resolution, conformance, and quality checks.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "nba-lakehouse",
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}

with DAG(
    dag_id="bronze_to_silver",
    default_args=default_args,
    description="Conform and merge Bronze sources into Silver dimensions and facts",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["transformation", "silver"],
) as dag:

    def _run_bronze_to_silver(**ctx):
        from jobs.transformations.bronze_to_silver import run_all
        counts = run_all()
        ctx["ti"].xcom_push(key="silver_counts", value=counts)

    def _log_summary(**ctx):
        counts = ctx["ti"].xcom_pull(task_ids="transform_bronze_to_silver", key="silver_counts")
        print(f"Silver transformation counts: {counts}")

    t_transform = PythonOperator(task_id="transform_bronze_to_silver", python_callable=_run_bronze_to_silver)
    t_summary = PythonOperator(task_id="silver_summary", python_callable=_log_summary)

    t_transform >> t_summary

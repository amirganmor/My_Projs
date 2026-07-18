"""
DAG: silver_to_gold
====================
Build Gold analytics marts and ML feature tables from Silver.
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
    dag_id="silver_to_gold",
    default_args=default_args,
    description="Build Gold analytics marts and ML feature tables",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["transformation", "gold"],
) as dag:

    def _run_silver_to_gold(**ctx):
        from jobs.transformations.silver_to_gold import run_all
        counts = run_all()
        ctx["ti"].xcom_push(key="gold_counts", value=counts)

    def _log_summary(**ctx):
        counts = ctx["ti"].xcom_pull(task_ids="transform_silver_to_gold", key="gold_counts")
        print(f"Gold transformation counts: {counts}")

    t_transform = PythonOperator(task_id="transform_silver_to_gold", python_callable=_run_silver_to_gold)
    t_summary = PythonOperator(task_id="gold_summary", python_callable=_log_summary)

    t_transform >> t_summary

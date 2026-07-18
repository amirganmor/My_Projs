"""
DAG: ingest_sources_to_bronze
==============================
Ingest all 6 source families into Bronze Iceberg tables.
  - NBA API cached JSON → bronze.nba_api_*
  - Advanced metrics CSV → bronze.advanced_player_metrics
  - Historical bulk CSV → bronze.historical_*
  - Shot chart data → bronze.shot_chart_*
  - PostgreSQL tables → bronze.contracts, bronze.injuries, bronze.rosters
  - MongoDB collections → bronze.mongo_*
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
    dag_id="ingest_sources_to_bronze",
    default_args=default_args,
    description="Ingest all source families into Bronze Iceberg tables",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["ingestion", "bronze"],
) as dag:

    def _ingest_api(**ctx):
        from jobs.ingestion.ingest_api import run_all
        counts = run_all()
        ctx["ti"].xcom_push(key="api_counts", value=counts)

    def _ingest_files(**ctx):
        from jobs.ingestion.ingest_files import run_all
        counts = run_all()
        ctx["ti"].xcom_push(key="file_counts", value=counts)

    def _ingest_postgres(**ctx):
        from jobs.ingestion.ingest_postgres import run_all
        counts = run_all()
        ctx["ti"].xcom_push(key="pg_counts", value=counts)

    def _ingest_mongo(**ctx):
        from jobs.ingestion.ingest_mongo import run_all
        counts = run_all()
        ctx["ti"].xcom_push(key="mongo_counts", value=counts)

    def _ingestion_summary(**ctx):
        ti = ctx["ti"]
        for key in ["api_counts", "file_counts", "pg_counts", "mongo_counts"]:
            val = ti.xcom_pull(key=key)
            print(f"  {key}: {val}")

    t_api = PythonOperator(task_id="ingest_nba_api", python_callable=_ingest_api)
    t_files = PythonOperator(task_id="ingest_files", python_callable=_ingest_files)
    t_pg = PythonOperator(task_id="ingest_postgres", python_callable=_ingest_postgres)
    t_mongo = PythonOperator(task_id="ingest_mongo", python_callable=_ingest_mongo)
    t_summary = PythonOperator(task_id="ingestion_summary", python_callable=_ingestion_summary, trigger_rule="all_done")

    [t_api, t_files, t_pg, t_mongo] >> t_summary

"""
DAG: seed_local_sources
========================
Load seed data into PostgreSQL and MongoDB source systems.
Verify all cached seed files are present.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "nba-lakehouse",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="seed_local_sources",
    default_args=default_args,
    description="Load seed CSV/JSON into Postgres and MongoDB, verify seed files",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,  # manual trigger only
    catchup=False,
    tags=["seed", "setup"],
) as dag:

    def _verify_seed_data(**ctx):
        from jobs.seed.verify_seed_data import verify_seed_data
        result = verify_seed_data()
        ctx["ti"].xcom_push(key="seed_verify", value=result)

    def _seed_postgres(**ctx):
        from jobs.seed.seed_postgres import seed_postgres
        counts = seed_postgres()
        ctx["ti"].xcom_push(key="pg_counts", value=counts)

    def _seed_mongo(**ctx):
        from jobs.seed.seed_mongo import seed_mongo
        counts = seed_mongo()
        ctx["ti"].xcom_push(key="mongo_counts", value=counts)

    def _summary(**ctx):
        ti = ctx["ti"]
        verify = ti.xcom_pull(task_ids="verify_seed_data", key="seed_verify") or {}
        pg = ti.xcom_pull(task_ids="seed_postgres", key="pg_counts") or {}
        mongo = ti.xcom_pull(task_ids="seed_mongo", key="mongo_counts") or {}
        print(f"Seed verification: {verify}")
        print(f"PostgreSQL rows: {pg}")
        print(f"MongoDB docs: {mongo}")

    t_verify = PythonOperator(task_id="verify_seed_data", python_callable=_verify_seed_data)
    t_pg = PythonOperator(task_id="seed_postgres", python_callable=_seed_postgres)
    t_mongo = PythonOperator(task_id="seed_mongo", python_callable=_seed_mongo)
    t_summary = PythonOperator(task_id="seed_summary", python_callable=_summary, trigger_rule="all_done")

    t_verify >> [t_pg, t_mongo] >> t_summary

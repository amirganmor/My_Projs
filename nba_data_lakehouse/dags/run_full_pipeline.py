"""
DAG: run_full_pipeline
=======================
Master orchestrator that triggers all 6 pipeline DAGs in sequence.
Each DAG waits for the previous one to complete before the next is triggered.

Execution order:
  1. seed_local_sources
  2. ingest_sources_to_bronze
  3. bronze_to_silver
  4. silver_to_gold
  5. train_models
  6. score_and_publish
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.sensors.external_task import ExternalTaskSensor

PIPELINE_DAGS = [
    "seed_local_sources",
    "ingest_sources_to_bronze",
    "bronze_to_silver",
    "silver_to_gold",
    "train_models",
    "score_and_publish",
]

default_args = {
    "owner": "nba-lakehouse",
    "retries": 0,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="run_full_pipeline",
    default_args=default_args,
    description="Master DAG – triggers all 6 pipeline stages in sequence",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["master", "orchestrator", "pipeline"],
) as dag:

    prev_task = None

    for dag_id in PIPELINE_DAGS:
        trigger = TriggerDagRunOperator(
            task_id=f"trigger_{dag_id}",
            trigger_dag_id=dag_id,
            wait_for_completion=True,
            poke_interval=15,
            allowed_states=["success"],
            failed_states=["failed"],
        )

        if prev_task:
            prev_task >> trigger

        prev_task = trigger

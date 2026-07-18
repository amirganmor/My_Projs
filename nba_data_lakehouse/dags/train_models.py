"""
DAG: train_models
==================
Train ML models for player value prediction and improvement prediction.
Logs experiments and artifacts to MLflow.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "nba-lakehouse",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="train_models",
    default_args=default_args,
    description="Train value and improvement ML models, log to MLflow",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["ml", "training"],
) as dag:

    def _train_value_model(**ctx):
        from jobs.training.train_value_model import train
        result = train()
        ctx["ti"].xcom_push(key="value_model_result", value=result)

    def _train_improvement_model(**ctx):
        from jobs.training.train_improvement_model import train
        result = train()
        ctx["ti"].xcom_push(key="improvement_model_result", value=result)

    def _training_summary(**ctx):
        ti = ctx["ti"]
        value = ti.xcom_pull(task_ids="train_value_model", key="value_model_result")
        improvement = ti.xcom_pull(task_ids="train_improvement_model", key="improvement_model_result")
        print(f"Value model: {value}")
        print(f"Improvement model: {improvement}")

    t_value = PythonOperator(task_id="train_value_model", python_callable=_train_value_model)
    t_improve = PythonOperator(task_id="train_improvement_model", python_callable=_train_improvement_model)
    t_summary = PythonOperator(task_id="training_summary", python_callable=_training_summary, trigger_rule="all_done")

    [t_value, t_improve] >> t_summary

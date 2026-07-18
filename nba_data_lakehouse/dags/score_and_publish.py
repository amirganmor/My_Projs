"""
DAG: score_and_publish
=======================
Score all three analytics use cases and publish results.
  1. Underrated players (value vs salary)
  2. Improvement candidates (breakout prediction)
  3. Trade target rankings (composite scoring)

Exports scored tables for dashboard consumption.
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
    dag_id="score_and_publish",
    default_args=default_args,
    description="Score underrated players, improvement candidates, and trade targets",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["scoring", "publishing"],
) as dag:

    def _score_underrated(**ctx):
        from jobs.scoring.score_underrated import score
        count = score()
        ctx["ti"].xcom_push(key="underrated_count", value=count)

    def _score_improvement(**ctx):
        from jobs.scoring.score_improvement import score
        count = score()
        ctx["ti"].xcom_push(key="improvement_count", value=count)

    def _score_trade_targets(**ctx):
        from jobs.scoring.build_trade_targets import score
        count = score()
        ctx["ti"].xcom_push(key="trade_count", value=count)

    def _export_for_dashboard(**ctx):
        """Export scored tables as Parquet to MinIO for dashboard consumption."""
        from jobs.common.schemas import GOLD_TABLES
        from jobs.common.spark_session import get_spark, stop_spark
        from jobs.common.minio_utils import get_s3_client
        import io

        spark = get_spark("export_dashboard")
        client = get_s3_client()
        bucket = "nba-lakehouse"

        tables_to_export = [
            ("scores_underrated_players", "exports/scores_underrated_players.parquet"),
            ("scores_improvement_candidates", "exports/scores_improvement_candidates.parquet"),
            ("scores_trade_targets", "exports/scores_trade_targets.parquet"),
            ("player_season_summary", "exports/player_season_summary.parquet"),
            ("data_quality_summary", "exports/data_quality_summary.parquet"),
            ("source_coverage_summary", "exports/source_coverage_summary.parquet"),
        ]

        for table_key, s3_key in tables_to_export:
            table = GOLD_TABLES.get(table_key)
            if not table:
                continue
            try:
                df = spark.table(table)
                pdf = df.toPandas()
                buf = io.BytesIO()
                pdf.to_parquet(buf, index=False)
                buf.seek(0)
                client.put_object(Bucket=bucket, Key=s3_key, Body=buf.getvalue())
                print(f"  Exported {table_key}: {len(pdf)} rows → s3://{bucket}/{s3_key}")
            except Exception as e:
                print(f"  Failed to export {table_key}: {e}")

        stop_spark(spark)

    def _publish_summary(**ctx):
        ti = ctx["ti"]
        print(f"  Underrated: {ti.xcom_pull(key='underrated_count')} players scored")
        print(f"  Improvement: {ti.xcom_pull(key='improvement_count')} candidates scored")
        print(f"  Trade targets: {ti.xcom_pull(key='trade_count')} players ranked")

    t_underrated = PythonOperator(task_id="score_underrated_players", python_callable=_score_underrated)
    t_improve = PythonOperator(task_id="score_improvement_candidates", python_callable=_score_improvement)
    t_trade = PythonOperator(task_id="score_trade_targets", python_callable=_score_trade_targets)
    t_export = PythonOperator(task_id="export_for_dashboard", python_callable=_export_for_dashboard)
    t_summary = PythonOperator(task_id="publish_summary", python_callable=_publish_summary)

    [t_underrated, t_improve, t_trade] >> t_export >> t_summary

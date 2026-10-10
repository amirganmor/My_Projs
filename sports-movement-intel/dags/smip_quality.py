"""Pipeline quality gate for a streamed replay session: batch/stream parity and Iceberg lineage."""

from __future__ import annotations

import os
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Param

SMIP = os.environ.get("SMIP_BIN", "smip")

with DAG(
    dag_id="smip_quality",
    description="Batch-vs-stream parity and lineage checks for one replay session",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    params={"match_id": Param("skillcorner:1886347", type="string"),
            "session_id": Param("demo-soccer-hero", type="string")},
    tags=["smip", "quality"],
) as dag:
    args = "--match {{ params.match_id }} --session {{ params.session_id }}"
    parity = BashOperator(task_id="batch_stream_parity", bash_command=f"{SMIP} batch parity {args}")
    lineage = BashOperator(task_id="iceberg_lineage", bash_command=f"{SMIP} lakehouse lineage {args}")
    parity >> lineage

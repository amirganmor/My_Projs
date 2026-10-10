"""Batch data lifecycle: download (resumable, byte-capped) -> verify checksums -> normalize -> catalog."""

from __future__ import annotations

import os
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Param

SMIP = os.environ.get("SMIP_BIN", "smip")

with DAG(
    dag_id="smip_data",
    description="Acquire and normalize historical tracking data (no live feeds)",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    params={"profile": Param("sample", enum=["sample", "research", "full"])},
    tags=["smip", "data"],
) as dag:
    download = BashOperator(task_id="download", bash_command=f"{SMIP} sources download --profile {{{{ params.profile }}}}")
    verify = BashOperator(task_id="verify_checksums", bash_command=f"{SMIP} sources verify")
    normalize = BashOperator(task_id="normalize", bash_command=f"{SMIP} sources normalize")
    catalog = BashOperator(task_id="catalog", bash_command=f"{SMIP} sources catalog")
    download >> verify >> normalize >> catalog

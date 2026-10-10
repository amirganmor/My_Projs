# Local → AWS mapping

Nothing here is deployed to AWS. This maps each local component to its managed equivalent and notes what
would change.

| local | AWS | notes |
|---|---|---|
| Kafka 4.3 (KRaft, single broker) | Amazon MSK (provisioned or Serverless) | 3 AZs, RF=3, `min.insync.replicas=2`; IAM auth; keep key = `session\|match` |
| replay service | ECS Fargate task or Lambda (short sessions) | reads normalized parquet from S3 |
| Spark Structured Streaming (local[*]) | EMR on EC2/EKS, or Glue Streaming | checkpoints on S3; `applyInPandasWithState` is supported on EMR 7.x / Spark 3.5+ |
| Iceberg REST catalog + S3 gateway | AWS Glue Data Catalog (Iceberg) or S3 Tables + S3 | the commit-tag idempotency works with any catalog |
| ClickHouse 25.8 | ClickHouse Cloud on AWS, or self-managed on EC2 | alternative: Athena over Iceberg for non-interactive paths |
| FastAPI + React | ECS Fargate behind ALB; static UI on S3 + CloudFront | `SMIP_PUBLIC_DEMO=1` for public endpoints |
| Airflow (orchestration profile) | Amazon MWAA | DAGs call the same `smip` CLI |
| local secrets / `.env` | Secrets Manager / SSM Parameter Store | no secrets are required by the default demo |
| docker healthchecks | ALB target health, CloudWatch alarms | |

## Cost drivers to watch

- **MSK:** broker-hours dominate at low volume. Serverless is simpler for bursty replay demos.
- **EMR / Glue streaming:** always-on compute. Size for one micro-batch per 5–10 s; the engine state per session is small.
- **S3 requests:** small Iceberg commits create many small files. Run compaction and snapshot expiry (not part of v0.1).
- **ClickHouse:** memory for `FINAL` reads. Pre-aggregated gold tables keep scans small.

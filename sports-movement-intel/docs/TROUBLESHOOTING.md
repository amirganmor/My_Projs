# Troubleshooting

## Build

- **`docker compose build` fails with a buildx / builder error on macOS:** use the Desktop builder:
  `BUILDX_BUILDER=desktop-linux docker compose build`.
- **Images are slow to build the first time:** Spark and ClickHouse images are large; later builds are cached.

## Memory

- The default stack needs about 6.5 GiB inside the Docker VM. Check with `docker stats`.
- **Do not run Airflow together with a streaming demo on an 8 GiB VM.** `make airflow` starts the
  `orchestration` profile. Stop `spark-stream` first, or raise the Docker VM memory.
- ClickHouse error `MEMORY_LIMIT_EXCEEDED` on large `FINAL` reads: narrow the query by session and match
  (every API query already does).

## ClickHouse

- **`ILLEGAL_AGGREGATION` or the wrong column used in `WHERE`:** a `SELECT` alias with the same name as a source
  column shadows it (for example `min(t_ms) AS t_ms`). Rename the alias, or run with
  `prefer_column_name_to_alias=1` (the analyst tools set it). In `HAVING`, repeat the aggregate expression.
- **Duplicate-looking rows:** tables are `ReplacingMergeTree`. Query with `FINAL`.

## Pipeline

- **A session never finishes (`ended` stays false):** check `docker compose logs spark-stream`. The
  processing-time timeout finalizes idle sessions after 120 s.
- **Parity mismatch:** run `smip batch parity --session <id>`. The report lists the first differing keys.
  Typical causes are an engine change without a `feature_version` bump, or a session that has not ended.
- **Kafka warning `Coordinator load in progress` at startup:** harmless; the producer retries.

## Local tooling

- **Background jobs die when a terminal closes:** run long replays in a terminal that stays open, or with `tmux`.
- **Playwright cannot find Chromium:** run `npx playwright install chromium` in `frontend/`, or set
  `PLAYWRIGHT_BROWSERS_PATH` to your browser cache (macOS: `~/Library/Caches/ms-playwright`).
- **The dashboard shows "not redistributable" / 404:** `SMIP_PUBLIC_DEMO=1` hides Metrica and NBA. Unset it for local work.

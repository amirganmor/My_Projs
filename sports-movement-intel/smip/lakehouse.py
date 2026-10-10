"""Iceberg lakehouse inspection through the REST catalog (pyiceberg; read-only).

Every table's files are plain objects under ./lakehouse/data/warehouse/<namespace>/<table>/ on the host,
served by the S3-compatible gateway. Maintenance (compaction, snapshot expiry, orphan removal) uses
Spark procedures in ``smip.spark.maintenance``.
"""

from __future__ import annotations

from collections import Counter

from smip.config import REPO_ROOT, get_settings


def catalog():
    from pyiceberg.catalog import load_catalog

    s = get_settings()
    return load_catalog("smip", **{
        "type": "rest", "uri": s.iceberg_rest_uri, "s3.endpoint": s.s3_endpoint,
        "s3.access-key-id": s.s3_access_key, "s3.secret-access-key": s.s3_secret_key,
        "s3.region": s.s3_region, "s3.path-style-access": "true",
    })


def local_path(location: str) -> str:
    return str(REPO_ROOT / "lakehouse" / "data" / location.removeprefix("s3://"))


def inspect(session_id: str | None = None) -> dict:
    cat = catalog()
    out = {}
    for ns in cat.list_namespaces():
        for ident in cat.list_tables(ns):
            t = cat.load_table(ident)
            name = ".".join(ident)
            snaps = t.snapshots()
            cur = t.current_snapshot()
            summary = cur.summary.additional_properties if cur and cur.summary else {}
            info = {
                "format_version": t.metadata.format_version,
                "location": t.location(), "local_path": local_path(t.location()),
                "partition_spec": str(t.spec()), "snapshots": len(snaps),
                "current_snapshot_id": cur.snapshot_id if cur else None,
                "total_records": int(summary.get("total-records", 0)),
                "total_data_files": int(summary.get("total-data-files", 0)),
                "total_files_size_bytes": int(summary.get("total-files-size", 0)),
                "commit_tags_by_query": dict(Counter(
                    (s.summary.additional_properties.get("smip.commit") or "untagged").split(":")[0]
                    for s in snaps if s.summary)),
            }
            if session_id and "session_id" in [f.name for f in t.schema().fields] + (
                    ["replay_session_id"] if "replay_session_id" in [f.name for f in t.schema().fields] else []):
                col = "session_id" if "session_id" in [f.name for f in t.schema().fields] else "replay_session_id"
                from pyiceberg.expressions import EqualTo

                info["session_rows"] = t.scan(row_filter=EqualTo(col, session_id), selected_fields=(col,)).to_arrow().num_rows
            out[name] = info
    return out


def lineage(session_id: str, match_id: str) -> dict:
    """Kafka offsets -> bronze -> silver -> gold row counts and snapshot tags for one replay session."""
    from pyiceberg.expressions import And, EqualTo

    cat = catalog()
    res = {"session_id": session_id, "match_id": match_id}
    br = cat.load_table("bronze.kafka_tracking_raw").scan(
        row_filter=And(EqualTo("replay_session_id", session_id), EqualTo("match_id", match_id)),
        selected_fields=("kafka_partition", "kafka_offset", "sequence", "valid", "batch_id")).to_arrow().to_pandas()
    res["bronze"] = {"records": len(br), "valid": int(br["valid"].sum()),
                     "kafka_partitions": sorted(br["kafka_partition"].unique().tolist()),
                     "kafka_offsets": [int(br["kafka_offset"].min()), int(br["kafka_offset"].max())] if len(br) else None,
                     "bronze_batches": sorted(br["batch_id"].unique().tolist())[:3] + ["..."]}
    for tname in ("silver.tracking_frames", "silver.tracking_positions", "gold.team_frame_metrics",
                  "gold.player_windows", "gold.team_windows", "gold.spatial_dwell"):
        t = cat.load_table(tname)
        fields = [f.name for f in t.schema().fields]
        sel = tuple(c for c in ("batch_id", "is_final", "feature_version") if c in fields)
        df = t.scan(row_filter=And(EqualTo("session_id", session_id), EqualTo("match_id", match_id)),
                    selected_fields=sel).to_arrow().to_pandas()
        entry = {"rows": len(df), "engine_batches": int(df["batch_id"].nunique()) if len(df) else 0}
        if "is_final" in df:
            entry["final_rows"] = int(df["is_final"].sum())
        if "feature_version" in df and len(df):
            entry["feature_version"] = sorted(df["feature_version"].unique().tolist())
        res[tname] = entry
    return res

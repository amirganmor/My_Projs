"""Batch/stream parity: final windows from the batch engine vs. the streaming session in ClickHouse."""

from __future__ import annotations

import numpy as np
import pandas as pd

from smip.features.batch import final_rows, run_match

CHECKS = {
    "player_windows": ("player_window", ["entity_id", "window"],
                       ["distance_m", "active_ms", "detected_ms", "hi_ms", "sprint_ms", "sprint_count",
                        "accel_count", "decel_count", "max_speed_mps", "in_poss_ms", "excluded_gap_ms"]),
    "team_windows": ("team_window", ["team_id", "window"],
                     ["n_frames", "n_sufficient", "mean_width_m", "mean_depth_m", "mean_hull_area_m2"]),
    "dwell": ("dwell", ["entity_id", "window", "cell_x", "cell_y"], ["dwell_ms"]),
}


def parity(match_id: str, session_id: str, rel_tol: float = 1e-4) -> dict:
    from smip.serving import ch

    batch = run_match(match_id, session_id="parity", chunk=2000, keep={v[0] for v in CHECKS.values()})
    report = {"match_id": match_id, "session_id": session_id, "tables": {}, "ok": True}
    for table, (kind, keys, metrics) in CHECKS.items():
        b = final_rows(batch[kind])[keys + metrics]
        s = ch.query_df(f"SELECT {', '.join(keys + metrics)} FROM {table} FINAL "
                        "WHERE session_id = {sid:String} AND match_id = {mid:String} AND is_final",
                        {"sid": session_id, "mid": match_id})
        m = b.merge(s, on=keys, how="outer", suffixes=("_batch", "_stream"), indicator=True)
        only_b, only_s = int((m["_merge"] == "left_only").sum()), int((m["_merge"] == "right_only").sum())
        both = m[m["_merge"] == "both"]
        diffs = {}
        for c in metrics:
            x = pd.to_numeric(both[f"{c}_batch"], errors="coerce").to_numpy(float)
            y = pd.to_numeric(both[f"{c}_stream"], errors="coerce").to_numpy(float)
            ok = np.isclose(x, y, rtol=rel_tol, atol=1e-3, equal_nan=True)
            if (~ok).any():
                diffs[c] = int((~ok).sum())
        passed = only_b == 0 and only_s == 0 and not diffs
        report["tables"][table] = {"batch_rows": len(b), "stream_rows": len(s), "only_batch": only_b,
                                   "only_stream": only_s, "mismatched_values": diffs, "pass": passed}
        report["ok"] &= passed
    return report

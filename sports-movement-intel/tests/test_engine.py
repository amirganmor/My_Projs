"""Engine correctness on SYNTHETIC fixtures (see tests/synthetic.py)."""

import json

import pandas as pd
import pytest
import synthetic

from smip.features.batch import final_rows, run_match
from smip.features.context import context_from_meta, sport_config
from smip.features.engine import MatchEngine
from smip.replay.frames import iter_frames, load_meta
from smip.replay.session import FaultConfig, ReplaySession, SessionSpec


@pytest.fixture(scope="module")
def clean(synthetic_match):
    return run_match(synthetic_match, chunk=700)


def _final_pw(out):
    return final_rows(out["player_window"]).sort_values(["entity_id", "window"]).reset_index(drop=True)


def test_one_final_row_per_window(clean):
    pw = _final_pw(clean)
    assert not pw.duplicated(["entity_id", "window"]).any()
    tw = final_rows(clean["team_window"])
    assert not tw.duplicated(["team_id", "window"]).any()
    # 2 periods x 150 s -> windows 0..2 per period (60 s windows)
    assert sorted(pw["window"].unique()) == [10000, 10001, 10002, 20000, 20001, 20002]


def test_dwell_reconciles_with_active_time(clean):
    pw = _final_pw(clean)
    dw = final_rows(clean["dwell"])
    assert int(dw["dwell_ms"].sum()) == int(pw["active_ms"].sum() - pw["no_cell_ms"].sum())
    assert not dw.duplicated(["entity_id", "window", "cell_x", "cell_y"]).any()


def test_distance_matches_circle_motion(clean):
    pw = _final_pw(clean)
    per = pw.groupby("entity_id").agg(d=("distance_m", "sum"), a=("active_ms", "sum"))
    for j in (3, 5, 14):
        row = per.loc[f"synthetic:player:{j}"]
        expected = synthetic.player_speed(j) * row["a"] / 1000.0
        assert row["d"] == pytest.approx(expected, rel=0.03)


def test_gap_breaks_segment_and_is_excluded(clean):
    pw = _final_pw(clean)
    p0 = pw[pw["entity_id"] == "synthetic:player:0"]
    assert p0["excluded_gap_ms"].sum() == pytest.approx(3100, abs=100)
    other = pw[pw["entity_id"] == "synthetic:player:1"]
    assert p0["active_ms"].sum() < other["active_ms"].sum()


def test_state_roundtrip_equals_single_run(synthetic_match, clean):
    """Simulates Spark: engine rebuilt from JSON state before every micro-batch."""
    meta = load_meta(synthetic_match)
    ctx, cfg = context_from_meta(meta), sport_config("soccer")
    state, rows = None, []
    msgs = list(iter_frames(synthetic_match)) + [{"end_of_stream": True, "sequence": 10**9}]
    for i in range(0, len(msgs), 333):
        eng = MatchEngine("s", ctx, cfg, json.loads(json.dumps(state)) if state else None)
        out = eng.ingest(msgs[i:i + 333])
        rows += out.get("player_window", [])
        state = eng.to_state()
    got = final_rows(pd.DataFrame(rows)).sort_values(["entity_id", "window"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(got.drop(columns=["version"]), _final_pw(clean).drop(columns=["version"]))


def _faulted_messages(match_id, producer, **faults):
    rs = ReplaySession(SessionSpec(match_id=match_id, speed=0, session_id=f"t-{abs(hash(str(faults)))}",
                                   seed=11, faults=FaultConfig(**faults)), producer=producer)
    rs.run()
    out = []
    for _, _, value in producer.records:
        try:
            out.append(json.loads(value))
        except json.JSONDecodeError:
            pass  # malformed records never reach the engine (quarantined by the stream job)
    return out


def test_faults_inside_reorder_buffer_do_not_change_results(synthetic_match, clean, fake_producer):
    msgs = _faulted_messages(synthetic_match, fake_producer, duplicate_rate=0.05, out_of_order_rate=0.05,
                             delay_rate=0.03, delay_frames=5, correction_rate=0.02, malformed_rate=0.01)
    flags = [f for m in msgs for f in m.get("quality_flags", [])]
    assert {"injected_duplicate", "injected_out_of_order", "injected_delay", "injected_correction"} <= set(flags)
    out = run_match(synthetic_match, messages=msgs, chunk=400)
    pd.testing.assert_frame_equal(_final_pw(out).drop(columns=["version"]),
                                  _final_pw(clean).drop(columns=["version"]))
    assert out["stats"].iloc[-1]["c_duplicate"] > 0


def test_delay_beyond_buffer_is_late_and_never_mutates(synthetic_match, fake_producer):
    msgs = _faulted_messages(synthetic_match, fake_producer, delay_rate=0.01, delay_frames=200)
    out = run_match(synthetic_match, messages=msgs, chunk=400)
    late = out["late"]
    assert (late["reason"] == "late_beyond_reorder_buffer").any()
    assert not _final_pw(out).duplicated(["entity_id", "window"]).any()


def test_after_end_of_stream_is_rejected(synthetic_match):
    meta = load_meta(synthetic_match)
    eng = MatchEngine("s", context_from_meta(meta), sport_config("soccer"))
    frames = list(iter_frames(synthetic_match, 0, 50))
    eng.ingest(frames + [{"end_of_stream": True, "sequence": 51}])
    out = eng.ingest([dict(frames[10], sequence=60)])
    assert out["late"][0]["reason"] == "after_end_of_stream"
    assert "player_window" not in out

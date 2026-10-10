import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from smip.sources.scores import parse_scoring_events, place_on_replay_time

HEADER = "GAME_ID,EVENTNUM,PERIOD,PCTIMESTRING,SCORE,SCOREMARGIN\n"


def test_parse_orientation_and_elapsed_clock():
    csv = HEADER + ("1,1,1,12:00,,\n"          # jump ball: no score
                    "1,2,1,11:30,0 - 2,2\n"    # home scores (SCORE is visitor - home)
                    "1,3,2,10:00,3 - 2,-1\n"   # visitor three in Q2
                    "1,4,5,4:00,3 - 4,1\n")    # overtime period is 5 minutes
    ev = parse_scoring_events(csv)
    assert [(e["home"], e["away"]) for e in ev] == [(2, 0), (2, 3), (4, 3)]
    assert ev[0]["mel"] == 30_000
    assert ev[1]["mel"] == 720_000 + 120_000
    assert ev[2]["mel"] == 4 * 720_000 + 60_000


def test_parse_rejects_inconsistent_margin():
    with pytest.raises(ValueError):
        parse_scoring_events(HEADER + "1,2,1,11:30,0 - 2,-2\n")


def test_place_on_first_frame_reaching_clock_and_flags_gaps(tmp_path):
    # period 1: game clock elapsed 0..10 s every second, then a tracking gap until 60 s
    mel = list(range(0, 11_000, 1000)) + [60_000]
    t = [1_000_000 + i * 1000 for i in range(len(mel))]
    pq.write_table(pa.table({"period": [1] * len(mel), "match_elapsed_ms": mel, "physical_time_ms": t}),
                   tmp_path / "frames.parquet")
    ev = [{"period": 1, "mel": 4_500, "home": 2, "away": 0},
          {"period": 1, "mel": 30_000, "home": 2, "away": 3},
          {"period": 2, "mel": 800_000, "home": 4, "away": 3}]
    out = place_on_replay_time(ev, tmp_path / "frames.parquet")
    assert [e["t_ms"] for e in out] == [1_005_000, 1_011_000]  # period 2 untracked: dropped
    assert [e["tracked"] for e in out] == [True, False]

"""Running score for SportVU replays from archived NBA.com play-by-play (source ``sportvu_pbp``).

SportVU tracking carries no score. For each normalized SportVU game this fetches the archived
play-by-play CSV, keeps the scoring events, and places each one on the replay's physical time
axis: the first tracked frame in that period whose elapsed game clock has reached the event.
Output: ``data/normalized/sportvu/<game_id>/scores.json`` (match.json is left untouched).
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone

import numpy as np
import pyarrow.parquet as pq

from smip.config import get_settings
from smip.sources import registry
from smip.sources.acquire import RAW, _fetcher
from smip.sources.adapters.sportvu import _period_len_s
from smip.sources.fetch import FetchError

log = logging.getLogger(__name__)
SOURCE = "sportvu_pbp"


def _clock_s(pctime: str) -> float:
    m, s = pctime.split(":")
    return int(m) * 60 + float(s)


def parse_scoring_events(text: str) -> list[dict]:
    """Scoring events in order: period, remaining game clock, elapsed game ms, home and away score.

    NBA.com ``SCORE`` is ``"<visitor> - <home>"``; ``SCOREMARGIN`` (home minus visitor) confirms it.
    """
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        score = (row.get("SCORE") or "").strip()
        if not score or " - " not in score:
            continue
        away, home = (int(x) for x in score.split(" - "))
        margin = (row.get("SCOREMARGIN") or "").strip()
        if margin and margin != "TIE" and int(margin) != home - away:
            raise ValueError(f"SCORE/SCOREMARGIN disagree at event {row.get('EVENTNUM')}: {score} vs {margin}")
        period = int(row["PERIOD"])
        clock = _clock_s(row["PCTIMESTRING"])
        base = sum(_period_len_s(p) for p in range(1, period)) * 1000
        out.append({"event_num": int(row["EVENTNUM"]), "period": period, "clock": row["PCTIMESTRING"],
                    "mel": base + int(round((_period_len_s(period) - clock) * 1000)), "home": home, "away": away})
    return out


def place_on_replay_time(events: list[dict], frames_path) -> list[dict]:
    """Attach ``t_ms`` (physical time) = first frame in the event's period whose game clock reached it."""
    f = pq.read_table(frames_path, columns=["period", "match_elapsed_ms", "physical_time_ms"]).to_pandas()
    f = f.dropna(subset=["match_elapsed_ms"]).sort_values("physical_time_ms")
    by_period = {}
    for p, g in f.groupby("period"):
        by_period[int(p)] = (np.maximum.accumulate(g["match_elapsed_ms"].to_numpy()), g["physical_time_ms"].to_numpy())
    placed = []
    for e in events:
        if e["period"] not in by_period:
            continue
        mel, t = by_period[e["period"]]
        i = min(int(np.searchsorted(mel, e["mel"], side="left")), len(t) - 1)
        # tracked = a frame exists within 2 s of game clock after the event (not inside a tracking gap)
        placed.append({**e, "t_ms": int(t[i]), "tracked": bool(0 <= mel[i] - e["mel"] <= 2000)})
    return placed


def enrich(force: bool = False) -> dict:
    s = get_settings()
    src = registry.source(SOURCE)
    rev = src["pinned_revision"]
    report: dict = {"written": [], "skipped": [], "failed": {}}
    fetcher = _fetcher()
    try:
        for mfile in sorted((s.normalized_dir / "sportvu").glob("*/match.json")):
            d = mfile.parent
            gid = json.loads(mfile.read_text())["source_match_id"]
            if (d / "scores.json").exists() and not force:
                report["skipped"].append(gid)
                continue
            rel = f"{src['path']}/{gid}.csv"
            try:
                rec = fetcher.download(SOURCE, rev, f"{RAW}/{src['repo']}/{rev}/{rel}", rel)
                raw = (s.raw_dir / SOURCE / rev / rel).read_text()
                events = place_on_replay_time(parse_scoring_events(raw), d / "frames.parquet")
                if not events:
                    raise ValueError("no scoring events")
                last = events[-1]
                (d / "scores.json").write_text(json.dumps({
                    "match_id": f"sportvu:{gid}", "source": SOURCE, "source_revision": rev,
                    "raw_asset": {"path": f"{SOURCE}/{rev}/{rel}", "sha256": rec.sha256},
                    "license": src["data_license"], "attribution": src["attribution"],
                    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "placement": "first tracked frame whose elapsed game clock reaches the event",
                    "final": {"home": last["home"], "away": last["away"]},
                    "events": [{k: e[k] for k in ("t_ms", "period", "clock", "home", "away", "tracked")} for e in events],
                }, indent=1))
                report["written"].append(gid)
                log.info("scores %s: final %s-%s, %d scoring events", gid, last["home"], last["away"], len(events))
            except (FetchError, ValueError, KeyError, OSError) as exc:
                report["failed"][gid] = f"{type(exc).__name__}: {exc}"
                log.error("scores %s failed: %s", gid, exc)
    finally:
        fetcher.close()
    return report

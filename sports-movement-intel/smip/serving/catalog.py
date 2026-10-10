"""Data catalog of normalized matches (capabilities, coverage, licensing) for the API and docs."""

from __future__ import annotations

import json
from functools import lru_cache

from smip.config import get_settings
from smip.sources.registry import load_registry


def list_matches() -> list[dict]:
    s = get_settings()
    reg = load_registry()["sources"]
    out = []
    if not s.normalized_dir.exists():
        return out
    for mfile in sorted(s.normalized_dir.glob("*/*/match.json")):
        meta = json.loads(mfile.read_text())
        q = json.loads((mfile.parent / "quality.json").read_text()) if (mfile.parent / "quality.json").exists() else {}
        src = reg.get(meta["source"], {})
        scores = _scores(mfile.parent)
        out.append({
            "match_id": meta["match_id"], "source": meta["source"], "sport": meta["sport"],
            "competition": meta.get("competition"), "season": meta.get("season"), "date": meta.get("date"),
            "home_team": meta["home_team"], "away_team": meta["away_team"],
            "score": meta.get("score") or (scores or {}).get("final"),
            "dimensions": meta["dimensions"], "sample_rate_hz": meta["sample_rate_hz"],
            "capabilities": meta["capabilities"], "counts": meta.get("counts"),
            "periods": meta["periods"],
            "quality": {k: v for k, v in q.items() if not isinstance(v, list)},
            "missing_segments": len(q.get("missing_segments_over_5s", [])),
            "license": src.get("data_license"), "attribution": src.get("attribution"),
            "redistributable_demo": bool(src.get("redistributable_demo")),
        })
    return out


def _scores(match_dir) -> dict | None:
    p = match_dir / "scores.json"
    return json.loads(p.read_text()) if p.exists() else None


def match_meta(match_id: str) -> dict:
    source, mid = match_id.split(":", 1)
    d = get_settings().normalized_dir / source / mid
    return _match_meta(match_id, (d / "scores.json").exists())


@lru_cache(maxsize=64)
def _match_meta(match_id: str, has_scores: bool) -> dict:
    source, mid = match_id.split(":", 1)
    d = get_settings().normalized_dir / source / mid
    meta = json.loads((d / "match.json").read_text())
    scores = _scores(d) if has_scores else None
    if scores:
        meta["score"] = meta.get("score") or scores["final"]
        meta["score_timeline"] = [{"t_ms": e["t_ms"], "home": e["home"], "away": e["away"]} for e in scores["events"]]
        meta["score_source"] = {"source": scores["source"], "license": scores["license"],
                                "attribution": scores["attribution"], "placement": scores["placement"]}
    return meta

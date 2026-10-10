"""Per-source asset planning (inventory / dry-run) and resumable download.

Each source is independent: a failure in one source is recorded and does not abort others.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from smip.config import get_settings
from smip.sources import registry
from smip.sources.fetch import BudgetExceeded, Fetcher, FetchError, parse_lfs_pointer

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
MEDIA = "https://media.githubusercontent.com/media"


@dataclass
class AssetSpec:
    source: str
    revision: str
    url: str
    rel_path: str
    size_bytes: int | None
    expected: str | None = None
    algo: str = "sha256"
    lfs: bool = False
    group: str = ""       # e.g. match id this asset belongs to


# --------------------------------------------------------------------------- github
def github_tree(fetcher: Fetcher, source_name: str, repo: str, rev: str) -> list[dict]:
    cache = get_settings().raw_dir / source_name / rev / "_github_tree.json"
    data = fetcher.get_json(f"{GITHUB_API}/repos/{repo}/git/trees/{rev}?recursive=1", cache_path=cache)
    if data.get("truncated"):
        log.warning("github tree for %s is truncated; listing may be incomplete", repo)
    return [e for e in data["tree"] if e["type"] == "blob"]


def _github_spec(fetcher: Fetcher, src_name: str, src: dict, entry: dict, group: str, resolve_lfs: bool) -> AssetSpec:
    repo, rev, path = src["repo"], src["pinned_revision"], entry["path"]
    spec = AssetSpec(src_name, rev, f"{RAW}/{repo}/{rev}/{path}", path, entry.get("size"), group=group)
    if resolve_lfs and entry.get("size", 0) < 1024:
        ptr = parse_lfs_pointer(fetcher.get_bytes(spec.url))
        if ptr:
            spec.url = f"{MEDIA}/{repo}/{rev}/{path}"
            spec.size_bytes, spec.expected, spec.algo, spec.lfs = ptr["size"], ptr["oid"], "sha256", True
    return spec


def plan_skillcorner(fetcher: Fetcher, cfg: dict, resolve_lfs: bool = True) -> list[AssetSpec]:
    src = registry.source("skillcorner")
    entries = github_tree(fetcher, "skillcorner", src["repo"], src["pinned_revision"])
    match_ids = sorted({e["path"].split("/")[2] for e in entries if e["path"].startswith("data/matches/")
                        and e["path"].count("/") == 3})
    n = cfg.get("matches", 1)
    if cfg.get("select"):
        chosen = [m for m in match_ids if m in cfg["select"]]
    else:
        chosen = match_ids if n == "all" else match_ids[: int(n)]
    specs = [_github_spec(fetcher, "skillcorner", src, e, "", False)
             for e in entries if e["path"] == "data/matches.json"]
    for e in entries:
        parts = e["path"].split("/")
        if len(parts) == 4 and parts[1] == "matches" and parts[2] in chosen:
            specs.append(_github_spec(fetcher, "skillcorner", src, e, parts[2], resolve_lfs))
    return specs


def plan_metrica(fetcher: Fetcher, cfg: dict, resolve_lfs: bool = True) -> list[AssetSpec]:
    src = registry.source("metrica")
    entries = github_tree(fetcher, "metrica", src["repo"], src["pinned_revision"])
    games = set(cfg.get("games", []))
    return [_github_spec(fetcher, "metrica", src, e, e["path"].split("/")[1], resolve_lfs)
            for e in entries if e["path"].startswith("data/") and e["path"].split("/")[1] in games]


def plan_sportvu(fetcher: Fetcher, cfg: dict, resolve_lfs: bool = True) -> list[AssetSpec]:
    src = registry.source("sportvu")
    entries = github_tree(fetcher, "sportvu", src["repo"], src["pinned_revision"])
    games = sorted((e for e in entries if e["path"].startswith(src["path"] + "/") and e["path"].endswith(".7z")),
                   key=lambda e: e["path"])
    n = cfg.get("games", 1)
    if cfg.get("select"):
        chosen = [e for e in games if Path(e["path"]).stem in cfg["select"]]
    else:
        chosen = games if n == "all" else games[: int(n)]
    return [_github_spec(fetcher, "sportvu", src, e, Path(e["path"]).stem, resolve_lfs) for e in chosen]


def plan_statsbomb(fetcher: Fetcher, cfg: dict, resolve_lfs: bool = False) -> list[AssetSpec]:
    src = registry.source("statsbomb")
    repo, rev = src["repo"], src["pinned_revision"]
    entries = {e["path"]: e for e in github_tree(fetcher, "statsbomb", repo, rev)}
    comps_entry = entries["data/competitions.json"]
    specs = [_github_spec(fetcher, "statsbomb", src, comps_entry, "", False)]
    comps = fetcher.get_json(specs[0].url, cache_path=get_settings().raw_dir / "statsbomb" / rev / "_competitions.json")
    wanted = cfg.get("competitions", [])
    pairs = sorted({(c["competition_id"], c["season_id"]) for c in comps}) if wanted == "all" else [tuple(p) for p in wanted]
    known = {(c["competition_id"], c["season_id"]): c for c in comps}
    for comp_id, season_id in pairs:
        if (comp_id, season_id) not in known:
            log.warning("statsbomb competition/season %s/%s not present at pinned revision", comp_id, season_id)
            continue
        mpath = f"data/matches/{comp_id}/{season_id}.json"
        mspec = _github_spec(fetcher, "statsbomb", src, entries[mpath], f"{comp_id}/{season_id}", False)
        specs.append(mspec)
        matches = fetcher.get_json(mspec.url, cache_path=get_settings().raw_dir / "statsbomb" / rev / f"_{comp_id}_{season_id}.json")
        for m in matches:
            mid = m["match_id"]
            for kind in cfg.get("kinds", ("events", "lineups", "three-sixty")):
                p = f"data/{kind}/{mid}.json"
                if p in entries:
                    specs.append(_github_spec(fetcher, "statsbomb", src, entries[p], str(mid), False))
    return specs


def plan_wyscout(fetcher: Fetcher, cfg: dict, resolve_lfs: bool = False) -> list[AssetSpec]:
    src = registry.source("wyscout")
    specs = []
    for key in cfg.get("include", []):
        art_id = src["figshare_articles"][key]
        art = fetcher.get_json(f"https://api.figshare.com/v2/articles/{art_id}",
                               cache_path=get_settings().raw_dir / "wyscout" / "_figshare" / f"{art_id}.json")
        rev = f"figshare-{art_id}-v{art.get('version', 1)}"
        for f in art["files"]:
            specs.append(AssetSpec("wyscout", rev, f["download_url"], f["name"], f["size"],
                                   expected=f.get("computed_md5") or f.get("supplied_md5"), algo="md5", group=key))
    return specs


PLANNERS = {
    "skillcorner": plan_skillcorner,
    "metrica": plan_metrica,
    "sportvu": plan_sportvu,
    "statsbomb": plan_statsbomb,
    "wyscout": plan_wyscout,
}
SELECTABLE = ("skillcorner", "sportvu")  # sources whose planners honour an explicit match selection


def selection_keys(match: list[str]) -> set[str]:
    """Accept bare keys or canonical ids (``skillcorner:2017461``)."""
    return {m.split(":", 1)[1] if ":" in m else m for m in match}


# ------------------------------------------------------------------ available games
def available(sources: list[str] | None = None) -> list[dict]:
    """Games published at each source's pinned revision, with local download / normalize status.

    ``key`` is what ``smip sources download --match`` expects. Listings come from cached GitHub
    trees and SkillCorner's matches.json; the network is used only if those caches are missing.
    """
    s = get_settings()
    rows: list[dict] = []
    fetcher = _fetcher()
    try:
        if not sources or "skillcorner" in sources:
            src = registry.source("skillcorner")
            rev = src["pinned_revision"]
            entries = github_tree(fetcher, "skillcorner", src["repo"], rev)
            ids = {e["path"].split("/")[2] for e in entries if e["path"].startswith("data/matches/")
                   and e["path"].count("/") == 3}
            meta = fetcher.get_json(f"{RAW}/{src['repo']}/{rev}/data/matches.json",
                                    cache_path=s.raw_dir / "skillcorner" / rev / "_matches.json")
            by_id = {str(m["id"]): m for m in meta}
            for mid in sorted(ids, key=lambda i: by_id.get(i, {}).get("date_time", ""), reverse=True):
                m = by_id.get(mid, {})
                rows.append({
                    "source": "skillcorner", "key": mid, "date": (m.get("date_time") or "")[:10],
                    "home": (m.get("home_team") or {}).get("short_name", "?"),
                    "away": (m.get("away_team") or {}).get("short_name", "?"),
                    "downloaded": (s.raw_dir / "skillcorner" / rev / "data" / "matches" / mid).is_dir(),
                    "match_id": f"skillcorner:{mid}"
                    if (s.normalized_dir / "skillcorner" / mid / "match.json").exists() else None,
                })
        if not sources or "sportvu" in sources:
            src = registry.source("sportvu")
            rev = src["pinned_revision"]
            normalized = {}
            for p in (s.normalized_dir / "sportvu").glob("*/match.json"):
                m = json.loads(p.read_text())
                normalized[(m.get("date"), m["home_team"].get("abbreviation"),
                            m["away_team"].get("abbreviation"))] = m["match_id"]
            for e in github_tree(fetcher, "sportvu", src["repo"], rev):
                path = e["path"]
                if not (path.startswith(src["path"] + "/") and path.endswith(".7z")):
                    continue
                stem = Path(path).stem
                # MM.DD.YYYY.AWAY.at.HOME; a few archive names carry a glued-on prefix
                m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})\.(\w+)\.at\.(\w+)$", stem)
                if not m:
                    continue
                mo, day, yr, away, home = m.groups()
                date = f"{yr}-{mo}-{day}"
                rows.append({
                    "source": "sportvu", "key": stem, "date": date, "home": home, "away": away,
                    "downloaded": (s.raw_dir / "sportvu" / rev / path).exists(),
                    "match_id": normalized.get((date, home, away)),
                })
    finally:
        fetcher.close()
    return rows


# ------------------------------------------------------------------------ run
def _fetcher(byte_budget: int | None = None) -> Fetcher:
    s = get_settings()
    return Fetcher(s.raw_dir, s.data_dir / "catalog", byte_budget=byte_budget)


def plan(profile_name: str, sources: list[str] | None = None,
         select: set[str] | None = None) -> dict[str, list[AssetSpec] | str]:
    prof = registry.profile(profile_name)
    out: dict[str, list[AssetSpec] | str] = {}
    fetcher = _fetcher()
    try:
        for name, planner in PLANNERS.items():
            if sources and name not in sources:
                continue
            if select and name not in SELECTABLE:
                continue
            if name not in prof:
                continue
            cfg = {**prof[name], "select": select} if select else prof[name]
            try:
                out[name] = planner(fetcher, cfg)
            except (FetchError, KeyError, ValueError) as exc:
                log.error("planning failed for %s: %s", name, exc)
                out[name] = f"error: {exc}"
    finally:
        fetcher.close()
    return out


def run_download(profile_name: str, sources: list[str] | None = None, max_bytes: int | None = None,
                 dry_run: bool = False, match: list[str] | None = None) -> dict:
    """``match`` downloads exactly those games (keys from ``smip sources available``); the profile's
    byte cap then applies only if ``max_bytes`` is given."""
    prof = registry.profile(profile_name)
    select = selection_keys(match) if match else None
    cap = max_bytes if max_bytes is not None else (None if select else prof.get("byte_cap"))
    plans = plan(profile_name, sources, select)
    s = get_settings()
    report: dict = {"profile": profile_name, "byte_cap": cap, "dry_run": dry_run,
                    "started_at": datetime.now(timezone.utc).isoformat(), "sources": {}}
    if select:
        found = {sp.group for specs in plans.values() if isinstance(specs, list) for sp in specs}
        report["selected"] = sorted(select & found)
        report["unmatched"] = sorted(select - found)
        if report["unmatched"]:
            log.warning("no game with key %s; see `smip sources available`", ", ".join(report["unmatched"]))
    already = sum(p.stat().st_size for p in s.raw_dir.rglob("*") if p.is_file() and not p.name.startswith("_")) \
        if s.raw_dir.exists() else 0
    for name, specs in plans.items():
        if isinstance(specs, str):
            report["sources"][name] = {"status": "failed", "error": specs}
            continue
        est = sum(sp.size_bytes or 0 for sp in specs)
        entry = {"assets": len(specs), "estimated_bytes": est, "groups": len({sp.group for sp in specs})}
        report["sources"][name] = entry
        if dry_run:
            entry["status"] = "planned"
            continue
        fetcher = _fetcher(byte_budget=None)
        done = failed = 0
        try:
            for sp in specs:
                local = s.raw_dir / sp.source / sp.revision / sp.rel_path
                existed = local.exists()
                if not existed and cap is not None and already + (sp.size_bytes or 0) > cap:
                    entry.setdefault("skipped_budget", 0)
                    entry["skipped_budget"] += 1
                    continue
                try:
                    fetcher.download(sp.source, sp.revision, sp.url, sp.rel_path, sp.expected, sp.algo,
                                     sp.size_bytes, sp.lfs)
                    if not local.exists():
                        raise FetchError("file missing after download")
                    if not existed:
                        already += local.stat().st_size
                    done += 1
                except (FetchError, BudgetExceeded) as exc:
                    log.error("%s: %s", sp.rel_path, exc)
                    failed += 1
                    entry.setdefault("errors", []).append(f"{sp.rel_path}: {exc}")
        finally:
            fetcher.close()
        entry.update(status="ok" if failed == 0 else "partial", downloaded=done, failed=failed)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    name = "match" if select else profile_name
    out = s.data_dir / "catalog" / f"download_report_{name}{'_dryrun' if dry_run else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    plan_path = s.data_dir / "catalog" / f"plan_{name}.json"
    plan_path.write_text(json.dumps({k: [asdict(x) for x in v] if isinstance(v, list) else v
                                     for k, v in plans.items()}, indent=1))
    return report

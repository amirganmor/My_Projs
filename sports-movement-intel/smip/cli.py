"""Typer CLI: `smip <group> <command>`. Make targets wrap these commands."""

from __future__ import annotations

import json
import logging

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)
sources_app = typer.Typer(no_args_is_help=True, help="Source inventory, download, verify, normalize.")
app.add_typer(sources_app, name="sources")


def _logging(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


@app.command()
def doctor() -> None:
    """Environment and dependency checks."""
    from smip.doctor import run_doctor

    ok = run_doctor()
    raise typer.Exit(0 if ok else 1)


@sources_app.command("list")
def sources_list() -> None:
    """List registered sources with license and access status."""
    from smip.sources.registry import load_registry

    reg = load_registry()
    for name, s in reg["sources"].items():
        typer.echo(f"{name:22} {s['priority']:3} {s['sport']:10} {s['access_status']:22} "
                   f"demo={'yes' if s.get('redistributable_demo') else 'no ':3}  data_license={s.get('data_license')}")


@sources_app.command("inspect")
def sources_inspect(name: str) -> None:
    """Show registry entry and discovered inventory for a source."""
    from smip.sources.catalog import load_catalog
    from smip.sources.registry import source

    typer.echo(json.dumps({"registry": source(name), "discovered": load_catalog().get("sources", {}).get(name)},
                          indent=2, default=str))


@sources_app.command("download")
def sources_download(
    profile: str = typer.Option("sample", help="sample | research | full"),
    only: str = typer.Option(None, help="comma-separated source names"),
    max_bytes: int = typer.Option(None, help="override profile byte cap"),
    dry_run: bool = typer.Option(False, help="plan and estimate storage only"),
    match: str = typer.Option(None, help="comma-separated game keys from `smip sources available` "
                                         "(SkillCorner and SportVU); downloads exactly these"),
    verbose: bool = False,
) -> None:
    """Resumable download of a profile, or of specific games with --match. Sources fail independently."""
    from smip.sources.acquire import run_download

    _logging(verbose)
    report = run_download(profile, _csv(only), max_bytes, dry_run, _csv(match))
    typer.echo(json.dumps(report, indent=2))
    if report.get("unmatched"):
        raise typer.Exit(1)


@sources_app.command("available")
def sources_available(
    only: str = typer.Option(None, help="skillcorner and/or sportvu"),
    search: str = typer.Option(None, help="case-insensitive filter on date, teams or key, e.g. 'auckland' or 'TOR'"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Games available to download, and which are already downloaded / normalized."""
    from smip.sources.acquire import available

    rows = available(_csv(only))
    if search:
        q = search.lower()
        rows = [r for r in rows if q in " ".join(str(r[k]) for k in ("key", "date", "home", "away")).lower()]
    if as_json:
        typer.echo(json.dumps(rows, indent=2))
        return
    typer.echo(f"{'source':12} {'key (use with --match)':24} {'date':10}  {'home v away':34} status")
    for r in rows:
        status = f"ready: {r['match_id']}" if r["match_id"] else ("downloaded" if r["downloaded"] else "-")
        typer.echo(f"{r['source']:12} {r['key']:24} {r['date']:10}  {r['home'] + ' v ' + r['away']:34} {status}")
    typer.echo(f"\n{len(rows)} games · '-' = not downloaded · 'downloaded' = run `smip sources normalize` · "
               "'ready' = replayable")


@sources_app.command("verify")
def sources_verify() -> None:
    """Re-hash every recorded raw asset and compare to its recorded sha256/expected checksum."""
    from smip.sources.catalog import verify_assets

    _logging()
    res = verify_assets()
    typer.echo(json.dumps(res, indent=2))
    raise typer.Exit(0 if res["mismatched"] == 0 and res["missing"] == 0 else 1)


@sources_app.command("normalize")
def sources_normalize(
    only: str = typer.Option(None, help="comma-separated source names"),
    match: str = typer.Option(None, help="comma-separated source match ids"),
    force: bool = False,
) -> None:
    """Normalize downloaded raw assets into canonical parquet contracts."""
    from smip.sources.normalize import normalize_all

    _logging()
    report = normalize_all(_csv(only), _csv(match), force)
    if not only or "sportvu" in _csv(only):
        from smip.sources.scores import enrich

        report["sportvu_scores"] = enrich()
    typer.echo(json.dumps(report, indent=2))


@sources_app.command("scores")
def sources_scores(force: bool = False) -> None:
    """Running score for normalized SportVU games from archived play-by-play (local only)."""
    from smip.sources.scores import enrich

    _logging()
    res = enrich(force)
    typer.echo(json.dumps(res, indent=2))
    raise typer.Exit(0 if not res["failed"] else 1)


@sources_app.command("catalog")
def sources_catalog() -> None:
    """Rebuild the data catalog / manifest lock and docs/DATA_SOURCES.md."""
    from smip.sources.catalog import build_catalog

    _logging()
    cat = build_catalog(write_docs=True)
    typer.echo(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "matches"}
                           for k, v in cat["sources"].items()}, indent=2))


replay_app = typer.Typer(no_args_is_help=True, help="Historical replay through Kafka.")
app.add_typer(replay_app, name="replay")


def _faults(dup: float, delay: float, delay_frames: int, drop: float, ooo: float, corr: float, malformed: float):
    from smip.replay.session import FaultConfig

    return FaultConfig(duplicate_rate=dup, delay_rate=delay, delay_frames=delay_frames, drop_rate=drop,
                       out_of_order_rate=ooo, correction_rate=corr, malformed_rate=malformed).validate()


@replay_app.command("start")
def replay_start(
    match: str = typer.Option(..., help="canonical match id, e.g. skillcorner:1886347"),
    speed: float = typer.Option(1.0, help="0.5, 1, 5, 20 ... ; 0 = unthrottled benchmark"),
    session: str = typer.Option(None, help="session id (default: new independent session)"),
    resume: bool = typer.Option(False, help="retry an existing session from its checkpoint"),
    seed: int = 7,
    dup: float = 0.0, delay: float = 0.0, delay_frames: int = 5, drop: float = 0.0, ooo: float = 0.0,
    corr: float = 0.0, malformed: float = 0.0,
    end_seq: int = typer.Option(None, help="stop after this sequence (partial replay)"),
    inline: bool = typer.Option(True, help="run in this process (False: send a control message to the service)"),
) -> None:
    """Start (or retry) a historical replay session."""
    from smip.replay.session import ReplaySession, SessionSpec, new_session_id

    _logging()
    faults = _faults(dup, delay, delay_frames, drop, ooo, corr, malformed)
    if not inline:
        from dataclasses import asdict

        from smip.replay.service import send_control

        sid = session or new_session_id(match)
        typer.echo(json.dumps(send_control("start", sid, match_id=match, speed=speed, seed=seed,
                                           faults=asdict(faults), resume=resume)))
        return
    rs = ReplaySession(SessionSpec(match_id=match, speed=speed, session_id=session, seed=seed, faults=faults,
                                   resume=resume, end_seq=end_seq))
    typer.echo(f"session_id={rs.session_id}")
    rs.run()
    typer.echo(json.dumps({"session_id": rs.session_id, "status": rs.status, "frames_sent": rs.frames_sent,
                           "last_seq": rs.last_seq}))


@replay_app.command("control")
def replay_control(session: str, command: str, speed: float = None) -> None:
    """Send pause | resume | speed | stop to the replay service."""
    from smip.replay.service import send_control

    typer.echo(json.dumps(send_control(command, session, speed=speed)))


@replay_app.command("serve")
def replay_serve() -> None:
    """Run the replay service (consumes the control topic)."""
    from smip.replay.service import serve

    _logging()
    serve()


lake_app = typer.Typer(no_args_is_help=True, help="Iceberg lakehouse inspection and maintenance.")
app.add_typer(lake_app, name="lakehouse")


@lake_app.command("inspect")
def lake_inspect(session: str = typer.Option(None)) -> None:
    """Tables, snapshots, files and host paths under ./lakehouse."""
    from smip.lakehouse import inspect

    typer.echo(json.dumps(inspect(session), indent=2, default=str))


@lake_app.command("lineage")
def lake_lineage(session: str = typer.Option(...), match: str = typer.Option(...)) -> None:
    """Kafka offsets -> bronze -> silver -> gold for one replay session."""
    from smip.lakehouse import lineage

    typer.echo(json.dumps(lineage(session, match), indent=2, default=str))


batch_app = typer.Typer(no_args_is_help=True, help="Batch engine: backfill and parity.")
app.add_typer(batch_app, name="batch")


@batch_app.command("parity")
def batch_parity(match: str = typer.Option(...), session: str = typer.Option(..., help="streamed session id")) -> None:
    """Compare batch final windows with the streaming session's final windows in ClickHouse."""
    from smip.features.parity import parity

    rep = parity(match, session)
    typer.echo(json.dumps(rep, indent=2))
    raise typer.Exit(0 if rep["ok"] else 1)


analyst_app = typer.Typer(no_args_is_help=True, help="Deterministic grounded analyst.")
app.add_typer(analyst_app, name="analyst")


@analyst_app.command("ask")
def analyst_ask(question: str, session: str = typer.Option(...), match: str = typer.Option(...),
                mode: str = "replay_time", as_of_ms: int = None) -> None:
    """Answer one question with the read-only tools."""
    from smip.analyst.router import ask

    r = ask(question, session, match, mode, as_of_ms)
    r.pop("data", None)
    typer.echo(json.dumps(r, indent=2, default=str))


@analyst_app.command("eval")
def analyst_eval(session: str = typer.Option("demo-soccer-hero"),
                 match: str = typer.Option("skillcorner:1886347")) -> None:
    """Routing, grounding, cutoff and refusal checks; writes data/demo/analyst_eval.json."""
    from smip.analyst.eval import run_eval
    from smip.config import get_settings

    rep = run_eval(session, match)
    out = get_settings().data_dir / "demo" / "analyst_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2))
    for c in rep["cases"]:
        typer.echo(f"{'PASS' if c['pass'] else 'FAIL'}  {c['question'][:60]:60}  {c['detail']}")
    typer.echo(f"{rep['passed']}/{rep['total']} passed")
    raise typer.Exit(0 if rep["passed"] == rep["total"] else 1)


ml_app = typer.Typer(no_args_is_help=True, help="Light ML: similar moments and shape change points.")
app.add_typer(ml_app, name="ml")


@ml_app.command("eval")
def ml_eval(session: str = typer.Option("demo-soccer-hero"), match: str = typer.Option("skillcorner:1886347"),
            k: int = 5) -> None:
    """Possession-state lift for similar moments + change-point summary; writes data/demo/ml_eval_<session>.json."""
    from smip.config import get_settings
    from smip.ml import changes, moments

    idx = moments.build_index(session, match)
    rep = {"similar_moments": moments.evaluate(idx, k) if idx else {"status": "no data"}}
    ch_ = changes.detect(session, match)
    per = {}
    for c in ch_["changes"]:
        per.setdefault(f"{c['team_id']}|p{c['period']}", 0)
        per[f"{c['team_id']}|p{c['period']}"] += 1
    rep["shape_changes"] = {"model": ch_["model"], "version": ch_["version"], "n_changes": len(ch_["changes"]),
                            "per_team_period": per, "features": ch_.get("features")}
    out = get_settings().data_dir / "demo" / f"ml_eval_{session}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2))
    typer.echo(json.dumps(rep, indent=2))


bench_app = typer.Typer(no_args_is_help=True, help="Measured benchmarks (writes docs/BENCHMARKS.md).")
app.add_typer(bench_app, name="bench")


@bench_app.command("run")
def bench_run(match: str = typer.Option("skillcorner:1886347"),
              latency_session: str = typer.Option("demo-soccer-hero")) -> None:
    """Unthrottled stream run + batch engine run + paced-session latency + docker memory."""
    from smip.bench import run

    _logging()
    out = run(match, latency_session)
    typer.echo(json.dumps({k: out[k] for k in ("stream", "batch", "latency")}, indent=2, default=str))


demo_app = typer.Typer(no_args_is_help=True, help="Reproducible demo sessions.")
app.add_typer(demo_app, name="demo")


@demo_app.command("seed")
def demo_seed(only: str = typer.Option(None, help="comma-separated: hero,faults,nba"),
              force: bool = typer.Option(False, help="re-run even if a completed session exists")) -> None:
    """Replay the demo sessions through the live pipeline, then verify parity and lineage for each."""
    from smip.demo import seed

    _logging()
    rep = seed(_csv(only), skip_existing=not force)
    typer.echo(json.dumps({k: {"ok": v["ok"], "parity": v["parity"]["ok"],
                               "silver_frames": v["lineage"]["silver.tracking_frames"]["rows"],
                               "source_frames": v["lineage"]["source_frames"]}
                           for k, v in rep["sessions"].items()}, indent=2))
    raise typer.Exit(0 if rep["ok"] else 1)


if __name__ == "__main__":
    app()

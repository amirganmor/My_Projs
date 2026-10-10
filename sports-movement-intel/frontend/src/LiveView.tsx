import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, fmt, matchClock, scoreAt, type ChangePoint, type Frame, type MatchMeta, type Moment, type Session } from "./api";
import { AnalystPanel } from "./AnalystPanel";
import { COLORS, frameAt } from "./geometry";
import { Stage, type Overlay } from "./Stage";
import { periodAt, Timeline } from "./Timeline";

const OVERLAYS: { k: Overlay; label: string; hint: string }[] = [
  { k: "trails", label: "Trails", hint: "last 3 s of served positions" },
  { k: "hulls", label: "Hulls", hint: "convex hull of outfield players" },
  { k: "defline", label: "Def. line", hint: "mean x of the 4 deepest outfield players" },
  { k: "voronoi", label: "Voronoi", hint: "geometric Voronoi (nearest player), not pitch control" },
  { k: "heatmap", label: "Heatmap", hint: "time-weighted dwell, attack-normalized (attacking →)" },
  { k: "labels", label: "Numbers", hint: "jersey numbers" },
];
const SPEEDS = [1, 2, 5, 10, 20];
const FEATURE_LABEL: Record<string, string> = {
  width_m: "Width", depth_m: "Depth", hull_area_m2: "Hull area", def_line_height_m: "Def. line", centroid_x: "Centroid x",
  spacing_hull_m2: "Spacing hull", mean_pairwise_m: "Mean pairwise", paint_count: "In paint", corner_count: "In corners",
};

const qp = new URLSearchParams(window.location.search);
const T0 = qp.has("t") ? Number(qp.get("t")) : null;

export function LiveView({ session, meta }: { session: Session; meta: MatchMeta }) {
  const sid = session.session_id, mid = meta.match_id, soccer = meta.sport === "soccer";
  const [frames, setFrames] = useState<Frame[]>([]);
  const [playhead, setPlayhead] = useState(T0 ?? 0);
  const [playing, setPlaying] = useState(!qp.has("paused"));
  const [follow, setFollow] = useState(T0 === null && session.status === "running");
  const [speed, setSpeed] = useState(soccer ? 5 : 2);
  const [cursor, setCursor] = useState<any>(null);
  const [overlays, setOverlays] = useState<Set<Overlay>>(new Set(
    (qp.get("overlays")?.split(",") as Overlay[] | undefined) ?? ["trails", "hulls", "defline", "labels"]));
  const [team, setTeam] = useState<any>(null);
  const [changes, setChanges] = useState<ChangePoint[]>([]);
  const [moments, setMoments] = useState<Moment[]>([]);
  const [simInfo, setSimInfo] = useState<any>(null);
  const [pick, setPick] = useState<string | null>(qp.get("pick"));
  const [heat, setHeat] = useState<any>(null);
  const [metric, setMetric] = useState(soccer ? "def_line_height_m" : "hull_area_m2");
  const loading = useRef(false);
  const ph = useRef(0); ph.current = playhead;
  const hz = meta.sample_rate_hz || 10;
  const players = useMemo(() => new Map(meta.players.map(p => [p.canonical_player_id, p])), [meta]);

  // ---- pipeline cursor, team windows and change points (slow poll)
  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const [c, tm, ch] = await Promise.all([api.cursor(sid, mid), api.teamMetrics(sid, mid), api.changes(sid, mid)]);
        if (!live) return;
        setCursor(c); setTeam(tm); setChanges(ch.changes ?? []);
      } catch { /* pipeline may still be warming up */ }
    };
    load(); const id = setInterval(load, 4000);
    return () => { live = false; clearInterval(id); };
  }, [sid, mid]);

  // ---- frame buffer: fetch around the playhead, append ahead
  const fetchFrom = useCallback(async (t: number, replace: boolean) => {
    if (loading.current) return;
    loading.current = true;
    try {
      const r = await api.frames(sid, mid, t, Math.round(hz * 45));
      setFrames(prev => {
        if (replace || !prev.length) return r.frames;
        const last = prev[prev.length - 1].seq;
        const merged = prev.concat(r.frames.filter(f => f.seq > last));
        return merged.length > hz * 150 ? merged.slice(merged.length - hz * 120) : merged;
      });
    } finally { loading.current = false; }
  }, [sid, mid, hz]);

  useEffect(() => { setFrames([]); fetchFrom(Math.max(0, (T0 ?? 0) - 3000), true); }, [sid, fetchFrom]);

  useEffect(() => {
    if (!frames.length) return;
    const first = frames[0].t, last = frames[frames.length - 1].t;
    if (playhead < first - 1000 || playhead > last + 8000) fetchFrom(playhead - 3000, true);
    else if (last - playhead < 12000) fetchFrom(last + 1, false);
  }, [playhead, frames, fetchFrom]);

  // ---- playback clock
  useEffect(() => {
    let raf = 0, prev = performance.now();
    const tick = (now: number) => {
      const dt = now - prev; prev = now;
      const c = cursor?.cursor_t;
      if (follow && c !== null && c !== undefined) setPlayhead(Math.max(0, c - 1500));
      else if (playing) setPlayhead(p => (c !== null && c !== undefined ? Math.min(p + dt * speed, c) : p + dt * speed));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, follow, cursor]);

  // ---- heatmap for picked player (or both teams)
  useEffect(() => {
    if (!overlays.has("heatmap")) return;
    const q = pick ? { entity_id: pick } : { team_id: meta.home_team.team_id };
    api.heatmap(sid, mid, { ...q, mode: "replay_time" }).then(setHeat).catch(() => setHeat(null));
  }, [overlays, pick, sid, mid, Math.floor(playhead / 60000)]);

  const idx = frames.length ? frameAt(frames, playhead) : 0;
  const fr = frames[idx];
  const period = fr?.period ?? periodAt(meta, playhead);
  const seek = (t: number) => { setFollow(false); setPlayhead(t); fetchFrom(Math.max(0, t - 3000), true); };
  const toggle = (k: Overlay) => setOverlays(s => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const findSimilar = async () => {
    const r = await api.similar(sid, mid, playhead);
    setSimInfo(r); setMoments(r.neighbours ?? []);
  };

  useEffect(() => { if (qp.has("similar") && frames.length) findSimilar(); }, [frames.length > 0]);

  const snap = useMemo(() => shapeAt(team?.series ?? [], playhead), [team, Math.floor(playhead / 2000)]);
  const avg = useMemo(() => shapeAvg(team?.windows ?? []), [team]);
  const home = meta.home_team, away = meta.away_team;
  const live = meta.score_timeline?.length ? scoreAt(meta.score_timeline, fr ? fr.t : playhead) : null;

  return (
    <div className="live">
      <div className="scoreboard">
        <div className="team home"><span className="swatch" style={{ background: COLORS.home }} />{home.name}</div>
        <div className="score" title={meta.score_source ? `${meta.score_source.attribution} · ${meta.score_source.placement}` : undefined}>
          {live ? <span>{live.home}<i>–</i>{live.away}</span>
            : meta.score ? <span>{meta.score.home}<i>–</i>{meta.score.away}</span> : <span className="vs">vs</span>}
          <div className="clock">{fr ? matchClock(meta, fr.t, period) : "--:--"}</div>
          {live && meta.score && <div className="score-note">live · final {meta.score.home}–{meta.score.away}</div>}
          {!live && meta.score && <div className="score-note">final score</div>}
        </div>
        <div className="team away">{away.name}<span className="swatch" style={{ background: COLORS.away }} /></div>
        <div className="sb-meta">
          <span className="badge replay">● HISTORICAL MATCH REPLAY</span>
          <span className="muted">{meta.competition} {meta.season} · {meta.source}{meta.redistributable_demo ? " · MIT" : " · local only"}</span>
        </div>
      </div>

      <div className="live-grid">
        <div className="stage-col">
          <div className="toolbar">
            <div className="seg">
              <button className={playing && !follow ? "on" : ""} onClick={() => { setFollow(false); setPlaying(p => !p); }}>{playing && !follow ? "❚❚" : "▶"}</button>
              {SPEEDS.map(s => <button key={s} className={speed === s && !follow ? "on" : ""} onClick={() => { setFollow(false); setSpeed(s); setPlaying(true); }}>{s}×</button>)}
              <button className={follow ? "on live-btn" : "live-btn"} onClick={() => setFollow(f => !f)} title="follow the pipeline's processed cursor">LIVE EDGE</button>
            </div>
            <div className="seg">
              {OVERLAYS.filter(o => soccer || o.k !== "defline").map(o =>
                <button key={o.k} title={o.hint} className={overlays.has(o.k) ? "on" : ""} onClick={() => toggle(o.k)}>{o.label}</button>)}
            </div>
          </div>
          <Stage meta={meta} frames={frames} idx={idx} overlays={overlays} heat={heat} highlight={pick} onPick={setPick} />
          <div className="stage-foot">
            <span>{overlays.has("voronoi") && "Voronoi = geometric nearest-player regions, not pitch control. "}
              {overlays.has("heatmap") && `Heatmap: ${pick ? players.get(pick)?.name ?? pick : `${meta.home_team.name} (click a player)`}, attack-normalized (attacking →), up to the processed cursor. `}
              {soccer && "Hollow markers = provider-extrapolated (not detected)."}</span>
            <span className="muted">frame seq {fr?.seq ?? "–"} · served from ClickHouse positions (Spark output)</span>
          </div>
          <Timeline meta={meta} playhead={playhead} cursor={cursor?.cursor_t ?? null} windows={team?.windows ?? []} metric={metric}
            changes={changes} moments={moments} onSeek={seek} />
          <div className="tl-controls">
            <span className="muted">timeline metric</span>
            {(soccer ? ["def_line_height_m", "width_m", "depth_m", "hull_area_m2"] : ["hull_area_m2", "width_m", "depth_m"]).map(m =>
              <button key={m} className={metric === m ? "chip on" : "chip"} onClick={() => setMetric(m)}>{FEATURE_LABEL[m]}</button>)}
            <span className="grow" />
            <span className="muted">processed to {cursor?.cursor_t != null ? matchClock(meta, cursor.cursor_t, periodAt(meta, cursor.cursor_t)) : "–"}
              {cursor?.ended ? " · session finalized" : ""}</span>
          </div>
        </div>

        <div className="side-col">
          <div className="panel">
            <div className="panel-h"><h3>Team shape</h3><span className="muted">pipeline team_frames · Δ vs match avg</span></div>
            <div className="shape-grid">
              <div />
              <div className="th" style={{ color: COLORS.home }}>{home.abbreviation ?? home.name.split(" ")[0]}</div>
              <div className="th" style={{ color: COLORS.away }}>{away.abbreviation ?? away.name.split(" ")[0]}</div>
              {(soccer ? ["width_m", "depth_m", "hull_area_m2", "def_line_height_m"] : ["width_m", "depth_m", "hull_area_m2", "spacing_hull_m2", "paint_count"]).map(k => (
                <ShapeRow key={k} k={k} label={FEATURE_LABEL[k]} a={snap[home.team_id]?.[k]} b={snap[away.team_id]?.[k]}
                  avgA={avg[home.team_id]?.[k]} avgB={avg[away.team_id]?.[k]} />))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-h"><h3>Shape shifts</h3><span className="muted">PELT change points · {changes.length}</span></div>
            <div className="list">
              {changes.slice().sort((a, b) => b.magnitude_z - a.magnitude_z).slice(0, 6).sort((a, b) => a.t_ms - b.t_ms).map(c => {
                const f = c.top_features[0];
                return (
                  <button key={c.evidence_id} className="list-item" onClick={() => seek(c.t_ms)}>
                    <span className="dot" style={{ background: c.team_id === home.team_id ? COLORS.home : COLORS.away }} />
                    <span className="mono">{matchClock(meta, c.t_ms, c.period)}</span>
                    <span>{FEATURE_LABEL[f.feature] ?? f.feature} {fmt(f.before)} → <b>{fmt(f.after)}</b></span>
                    <span className="muted">{c.magnitude_z.toFixed(1)}σ</span>
                  </button>);
              })}
              {!changes.length && <div className="muted small">no shifts detected yet</div>}
            </div>
          </div>

          <div className="panel">
            <div className="panel-h"><h3>Similar moments</h3><button className="chip on" onClick={findSimilar}>find like {fr ? matchClock(meta, fr.t, period) : "now"}</button></div>
            <div className="list">
              {moments.map(m => (
                <button key={m.t_ms} className="list-item" onClick={() => seek(m.t_ms)}>
                  <span className="dot" style={{ background: COLORS.accent }} />
                  <span className="mono">{matchClock(meta, m.t_ms, m.period)}</span>
                  <span className="bar"><i style={{ width: `${Math.round((m.similarity ?? 0) * 100)}%` }} /></span>
                  <span className="muted">{m.possession_label ? (m.possession_label === home.team_id ? home.name : away.name) + " ball" : "no clear poss."}</span>
                </button>))}
              {simInfo && <div className="muted small">kNN over 10 s team-shape vectors · {simInfo.index_size} moments indexed · ±30 s excluded · geometric similarity, not tactical equivalence</div>}
              {!simInfo && <div className="muted small">Retrieves moments whose team shape over the last 10 s most resembles the playhead.</div>}
            </div>
          </div>

          <AnalystPanel sid={sid} meta={meta} playhead={playhead} onJump={seek} initial={qp.get("ask")} />
        </div>
      </div>
    </div>
  );
}

function ShapeRow({ k, label, a, b, avgA, avgB }: { k: string; label: string; a?: number | null; b?: number | null; avgA?: number; avgB?: number }) {
  const unit = k.endsWith("m2") ? "m²" : k.endsWith("_m") ? "m" : "";
  const d = (v?: number | null, m?: number) => (v == null || m == null ? null : v - m);
  const cell = (v?: number | null, m?: number) => {
    const dv = d(v, m);
    return (
      <div className="td">
        <span className="big">{v == null ? "–" : v.toFixed(k.endsWith("m2") ? 0 : 1)}</span><span className="unit">{unit}</span>
        {dv !== null && <span className={dv >= 0 ? "delta up" : "delta down"}>{dv >= 0 ? "+" : ""}{dv.toFixed(k.endsWith("m2") ? 0 : 1)}</span>}
      </div>);
  };
  return <><div className="tl">{label}</div>{cell(a, avgA)}{cell(b, avgB)}</>;
}

function shapeAt(series: any[], t: number): Record<string, Record<string, number | null>> {
  const out: Record<string, Record<string, number | null>> = {};
  for (const r of series) {
    if (r.t_ms > t || !r.sufficient) continue;
    out[r.team_id] = r;
  }
  return out;
}

function shapeAvg(windows: any[]): Record<string, Record<string, number>> {
  const acc: Record<string, Record<string, [number, number]>> = {};
  for (const w of windows) {
    for (const k of ["width_m", "depth_m", "hull_area_m2", "def_line_height_m"]) {
      const v = w[`mean_${k}`];
      if (v == null) continue;
      const a = ((acc[w.team_id] ??= {})[k] ??= [0, 0]);
      a[0] += v * w.n_sufficient; a[1] += w.n_sufficient;
    }
  }
  const out: Record<string, Record<string, number>> = {};
  for (const [tm, ks] of Object.entries(acc)) out[tm] = Object.fromEntries(Object.entries(ks).map(([k, [s, n]]) => [k, n ? s / n : NaN]));
  return out;
}

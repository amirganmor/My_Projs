import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmt, km, type MatchMeta, type Session } from "./api";
import { COLORS } from "./geometry";

type Key = "distance_m" | "distance_per_active_min_m" | "hi_distance_m" | "sprints" | "max_speed_mps" | "detected_share" | "active_ms";
const COLS: { k: Key; label: string; f: (v: any) => string; hint?: string }[] = [
  { k: "distance_m", label: "Distance km", f: v => km(v) },
  { k: "distance_per_active_min_m", label: "m / min", f: v => fmt(v, 0), hint: "distance per active minute" },
  { k: "hi_distance_m", label: "HSR m", f: v => fmt(v, 0), hint: "distance above the high-speed threshold" },
  { k: "sprints", label: "Sprints", f: v => String(v) },
  { k: "max_speed_mps", label: "Top km/h", f: v => fmt(v * 3.6, 1), hint: "max of causal EMA-smoothed speed" },
  { k: "active_ms", label: "Min", f: v => fmt(v / 60000, 0) },
  { k: "detected_share", label: "Detected", f: v => (v == null ? "n/a" : `${Math.round(v * 100)}%`), hint: "share of time directly detected (rest extrapolated)" },
];

export function PlayersView({ session, meta }: { session: Session; meta: MatchMeta }) {
  const [rows, setRows] = useState<any[]>([]);
  const [sort, setSort] = useState<Key>("distance_m");
  const [team, setTeam] = useState<string>("");
  const [heat, setHeat] = useState<Record<string, any>>({});
  const sid = session.session_id, mid = meta.match_id;

  useEffect(() => { api.players(sid, mid).then(r => setRows(r.players)).catch(() => setRows([])); }, [sid, mid]);
  useEffect(() => {
    let live = true;
    (async () => {
      const ids = rows.filter(r => r.active_ms > 0).map(r => r.entity_id);
      for (let i = 0; i < ids.length; i += 6) {
        const chunk = await Promise.all(ids.slice(i, i + 6).map(id => api.heatmap(sid, mid, { entity_id: id, mode: "post_match" }).then(h => [id, h] as const).catch(() => null)));
        if (!live) return;
        setHeat(h => ({ ...h, ...Object.fromEntries(chunk.filter(Boolean) as any) }));
      }
    })();
    return () => { live = false; };
  }, [rows, sid, mid]);

  const list = useMemo(() => rows.filter(r => r.active_ms > 60000 && (!team || r.team_id === team))
    .sort((a, b) => (b[sort] ?? -1) - (a[sort] ?? -1)), [rows, sort, team]);
  const max = useMemo(() => Object.fromEntries(COLS.map(c => [c.k, Math.max(1e-9, ...list.map(r => r[c.k] ?? 0))])), [list]);
  const home = meta.home_team.team_id;

  return (
    <div className="players-view">
      <div className="view-h">
        <div>
          <h2>Players</h2>
          <div className="muted">Aggregated from 60 s player windows written by the streaming engine · click a header to sort</div>
        </div>
        <div className="seg">
          <button className={!team ? "on" : ""} onClick={() => setTeam("")}>Both</button>
          <button className={team === home ? "on" : ""} onClick={() => setTeam(home)}>{meta.home_team.name}</button>
          <button className={team === meta.away_team.team_id ? "on" : ""} onClick={() => setTeam(meta.away_team.team_id)}>{meta.away_team.name}</button>
        </div>
      </div>
      <table className="ptable">
        <thead>
          <tr>
            <th>#</th><th>Player</th><th>Pos</th>
            {COLS.map(c => <th key={c.k} title={c.hint} className={sort === c.k ? "sorted" : ""} onClick={() => setSort(c.k)}>{c.label}</th>)}
            <th>Occupancy (attacking →)</th>
          </tr>
        </thead>
        <tbody>
          {list.map((r, i) => (
            <tr key={r.entity_id}>
              <td className="muted">{i + 1}</td>
              <td><span className="dot" style={{ background: r.team_id === home ? COLORS.home : COLORS.away }} />
                <span className="jersey">{r.jersey ?? ""}</span> {r.name ?? r.entity_id.split(":").pop()}</td>
              <td className="muted">{r.position ?? ""}</td>
              {COLS.map(c => (
                <td key={c.k} className="num">
                  <div className="cellbar"><i style={{ width: `${Math.max(0, Math.min(100, ((r[c.k] ?? 0) / max[c.k]) * 100))}%`, background: r.team_id === home ? COLORS.home : COLORS.away }} /></div>
                  <span>{r[c.k] == null ? "–" : c.f(r[c.k])}</span>
                </td>))}
              <td><MiniHeat meta={meta} h={heat[r.entity_id]} /></td>
            </tr>))}
        </tbody>
      </table>
      <div className="muted small">Distances use causal EMA-smoothed positions and exclude gaps above the sport's max gap. Metrica players are anonymized by the provider and stay anonymous.</div>
    </div>
  );
}

function MiniHeat({ meta, h }: { meta: MatchMeta; h: any }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const w = 132, ht = Math.round(w * meta.dimensions.width_m / meta.dimensions.length_m);
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = w * dpr; cv.height = ht * dpr; cv.style.width = `${w}px`; cv.style.height = `${ht}px`;
    const ctx = cv.getContext("2d")!; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = meta.sport === "soccer" ? "#0d281b" : "#2a1f15"; ctx.fillRect(0, 0, w, ht);
    if (h?.cells?.length) {
      const { nx, ny } = h.grid; const mx = Math.max(...h.cells.map((c: any) => c.dwell_ms));
      for (const c of h.cells) {
        const v = Math.sqrt(c.dwell_ms / mx);
        if (v < 0.2) continue;
        ctx.fillStyle = `rgba(250, ${Math.round(204 - 150 * v)}, 21, ${0.1 + 0.85 * v})`;
        ctx.fillRect((c.cell_x / nx) * w, ht - ((c.cell_y + 1) / ny) * ht, w / nx + 0.5, ht / ny + 0.5);
      }
    }
    ctx.strokeStyle = "rgba(255,255,255,0.35)"; ctx.strokeRect(0.5, 0.5, w - 1, ht - 1);
    ctx.beginPath(); ctx.moveTo(w / 2, 0); ctx.lineTo(w / 2, ht); ctx.stroke();
  }, [h, meta, w, ht]);
  return <canvas ref={ref} />;
}

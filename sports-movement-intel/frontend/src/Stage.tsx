import { useEffect, useRef } from "react";
import type { Frame, MatchMeta, PlayerMeta } from "./api";
import { COLORS, hull, withAlpha, type Pt } from "./geometry";

// Frames are drawn exactly as served by the pipeline (no interpolation). Hollow markers are
// provider-extrapolated positions (not directly detected).

export type Overlay = "trails" | "hulls" | "defline" | "voronoi" | "heatmap" | "labels";

interface Props {
  meta: MatchMeta; frames: Frame[]; idx: number; overlays: Set<Overlay>;
  heat?: { cells: { cell_x: number; cell_y: number; dwell_ms: number }[]; grid: { nx: number; ny: number } } | null;
  highlight?: string | null; onPick?: (entityId: string | null) => void;
}

const PAD = 26;

export function Stage({ meta, frames, idx, overlays, heat, highlight, onPick }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const L = meta.dimensions.length_m, W = meta.dimensions.width_m;
  const soccer = meta.sport === "soccer";
  const players = useRef(new Map<string, PlayerMeta>());
  players.current = new Map(meta.players.map(p => [p.canonical_player_id, p]));
  const lastPts = useRef<{ id: string; x: number; y: number }[]>([]);

  useEffect(() => {
    const cv = ref.current, box = wrap.current;
    if (!cv || !box) return;
    // fit both width and a viewport-derived height so the timeline stays above the fold
    const maxH = Math.max(320, window.innerHeight - 400);
    const cssW = Math.min(box.clientWidth, (maxH - 2 * PAD) * (L / W) + 2 * PAD);
    const scale = (cssW - 2 * PAD) / L, h = W * scale + 2 * PAD;
    const dpr = window.devicePixelRatio || 1;
    cv.width = cssW * dpr; cv.height = h * dpr; cv.style.width = `${cssW}px`; cv.style.height = `${h}px`;
    const ctx = cv.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const P = (x: number, y: number): Pt => [PAD + (x + L / 2) * scale, PAD + (W / 2 - y) * scale];
    const home = meta.home_team.team_id;
    const col = (team: string) => (team === home ? COLORS.home : COLORS.away);

    // ---- surface
    if (soccer) drawPitch(ctx, P, L, W, scale, cssW, h); else drawCourt(ctx, P, L, W, scale, cssW, h);

    const fr = frames[idx];
    if (!fr) { lastPts.current = []; return; }
    const period = meta.periods.find(p => p.period === fr.period);
    const dir = (team: string) => period?.attack_direction?.[team] ?? (team === home ? 1 : -1);
    const ents = fr.ents.filter(e => e[1] !== "ball" && !Number.isNaN(e[3]));
    const ball = fr.ents.find(e => e[1] === "ball");
    const isGK = (id: string) => !!players.current.get(id)?.is_goalkeeper;

    // ---- geometric Voronoi (nearest player per cell)
    if (overlays.has("voronoi") && ents.length > 3) {
      const cell = soccer ? 1.5 : 0.6;
      const nx = Math.ceil(L / cell), ny = Math.ceil(W / cell);
      for (let i = 0; i < nx; i++) for (let j = 0; j < ny; j++) {
        const x = -L / 2 + (i + 0.5) * cell, y = -W / 2 + (j + 0.5) * cell;
        let best = Infinity, team = "";
        for (const e of ents) { const d = (e[3] - x) ** 2 + (e[4] - y) ** 2; if (d < best) { best = d; team = e[2]; } }
        const [px, py] = P(x - cell / 2, y + cell / 2);
        ctx.fillStyle = withAlpha(col(team), team === home ? 0.16 : 0.24);
        ctx.fillRect(px, py, cell * scale + 0.5, cell * scale + 0.5);
      }
    }

    // ---- heatmap (attack-normalized: team attacks toward +x / right)
    if (overlays.has("heatmap") && heat?.cells?.length) {
      const max = Math.max(...heat.cells.map(c => c.dwell_ms));
      const cw = L / heat.grid.nx, ch = W / heat.grid.ny;
      for (const c of heat.cells) {
        const v = c.dwell_ms / max;
        if (v < 0.06) continue;
        const [px, py] = P(-L / 2 + c.cell_x * cw, -W / 2 + (c.cell_y + 1) * ch);
        ctx.fillStyle = `rgba(250, ${Math.round(204 - 170 * v)}, 21, ${0.12 + 0.68 * Math.pow(v, 0.7)})`;
        ctx.fillRect(px, py, cw * scale + 0.5, ch * scale + 0.5);
      }
    }

    // ---- hulls + defensive line per team
    const teams = [meta.home_team.team_id, meta.away_team.team_id];
    for (const tm of teams) {
      const own = ents.filter(e => e[2] === tm && !(soccer && isGK(e[0])));
      if (overlays.has("hulls") && own.length >= 3) {
        const hp = hull(own.map(e => [e[3], e[4]] as Pt)).map(([x, y]) => P(x, y));
        ctx.beginPath(); hp.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath();
        ctx.fillStyle = withAlpha(col(tm), 0.13); ctx.fill();
        ctx.strokeStyle = withAlpha(col(tm), 0.75); ctx.lineWidth = 1.4; ctx.setLineDash([]); ctx.stroke();
      }
      if (soccer && overlays.has("defline") && own.length >= 6) {
        const d = dir(tm);
        const deep = own.map(e => e[3]).sort((a, b) => a * d - b * d).slice(0, 4);
        const lx = deep.reduce((a, b) => a + b, 0) / deep.length;
        const [x0, y0] = P(lx, W / 2), [, y1] = P(lx, -W / 2);
        ctx.strokeStyle = withAlpha(col(tm), 0.9); ctx.lineWidth = 1.6; ctx.setLineDash([6, 5]);
        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0, y1); ctx.stroke(); ctx.setLineDash([]);
        const height = lx * d + L / 2;
        ctx.fillStyle = withAlpha(col(tm), 0.95); ctx.font = "600 10px Inter, system-ui";
        ctx.fillText(`line ${height.toFixed(0)} m`, x0 + 4, tm === home ? y0 + 12 : y1 - 5);
      }
    }

    // ---- trails (last ~3 s of served frames)
    if (overlays.has("trails")) {
      const hz = meta.sample_rate_hz || 10;
      const back = Math.round(hz * 3);
      const tracks = new Map<string, Pt[]>();
      for (let k = Math.max(0, idx - back); k <= idx; k++) {
        const f = frames[k];
        if (!f || fr.t - f.t > 4000) continue;
        for (const e of f.ents) {
          if (Number.isNaN(e[3])) continue;
          const arr = tracks.get(e[0]) ?? []; arr.push(P(e[3], e[4])); tracks.set(e[0], arr);
        }
      }
      for (const [id, pts] of tracks) {
        const e = fr.ents.find(x => x[0] === id);
        if (!e || pts.length < 2) continue;
        const c = e[1] === "ball" ? COLORS.ball : col(e[2]);
        for (let k = 1; k < pts.length; k++) {
          ctx.strokeStyle = withAlpha(c, (k / pts.length) * (e[1] === "ball" ? 0.8 : 0.55));
          ctx.lineWidth = e[1] === "ball" ? 2 : 2.2;
          ctx.beginPath(); ctx.moveTo(...pts[k - 1]); ctx.lineTo(...pts[k]); ctx.stroke();
        }
      }
    }

    // ---- players
    const r = Math.max(soccer ? 6.5 : 7.5, (soccer ? 0.9 : 0.35) * scale);
    lastPts.current = [];
    for (const e of ents) {
      const [x, y] = P(e[3], e[4]);
      const c = col(e[2]);
      const pm = players.current.get(e[0]);
      const hi = highlight === e[0];
      lastPts.current.push({ id: e[0], x, y });
      if (hi) { ctx.beginPath(); ctx.arc(x, y, r + 6, 0, Math.PI * 2); ctx.fillStyle = withAlpha("#ffffff", 0.18); ctx.fill(); }
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
      if (e[5] || !soccer) { ctx.fillStyle = c; ctx.fill(); ctx.strokeStyle = pm?.is_goalkeeper ? "#fef08a" : "rgba(255,255,255,0.85)"; ctx.lineWidth = 1.3; ctx.stroke(); }
      else { ctx.fillStyle = withAlpha(c, 0.25); ctx.fill(); ctx.strokeStyle = c; ctx.setLineDash([2, 2]); ctx.lineWidth = 1.3; ctx.stroke(); ctx.setLineDash([]); }
      if (overlays.has("labels") && pm?.jersey) {
        ctx.fillStyle = e[5] || !soccer ? "#0b1020" : c; ctx.font = `700 ${Math.round(r * 1.05)}px Inter, system-ui`;
        ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(pm.jersey, x, y + 0.5);
        ctx.textAlign = "start"; ctx.textBaseline = "alphabetic";
      }
    }
    if (ball && !Number.isNaN(ball[3])) {
      const [x, y] = P(ball[3], ball[4]);
      ctx.shadowColor = COLORS.ball; ctx.shadowBlur = 14;
      ctx.beginPath(); ctx.arc(x, y, soccer ? 4.2 : 5, 0, Math.PI * 2); ctx.fillStyle = COLORS.ball; ctx.fill();
      ctx.shadowBlur = 0; ctx.strokeStyle = "#1f2937"; ctx.lineWidth = 1; ctx.stroke();
    }
  }, [meta, frames, idx, overlays, heat, highlight, L, W, soccer]);

  const click = (ev: React.MouseEvent) => {
    if (!onPick || !ref.current) return;
    const b = ref.current.getBoundingClientRect();
    const x = ev.clientX - b.left, y = ev.clientY - b.top;
    let best: string | null = null, bd = 18 ** 2;
    for (const p of lastPts.current) { const d = (p.x - x) ** 2 + (p.y - y) ** 2; if (d < bd) { bd = d; best = p.id; } }
    onPick(best);
  };

  return <div ref={wrap} className="stage"><canvas ref={ref} onClick={click} /></div>;
}

type Proj = (x: number, y: number) => Pt;

function drawPitch(ctx: CanvasRenderingContext2D, P: Proj, L: number, W: number, s: number, w: number, h: number) {
  ctx.fillStyle = "#0a1f16"; ctx.fillRect(0, 0, w, h);
  const stripes = 14;
  for (let i = 0; i < stripes; i++) {
    const [x0, y0] = P(-L / 2 + (i * L) / stripes, W / 2);
    ctx.fillStyle = i % 2 ? "#0f2d1f" : "#0d281b";
    ctx.fillRect(x0, y0, (L / stripes) * s + 0.5, W * s);
  }
  ctx.strokeStyle = "rgba(255,255,255,0.55)"; ctx.lineWidth = 1.4;
  const rect = (x0: number, y0: number, x1: number, y1: number) => { const [a, b] = P(x0, y0), [c, d] = P(x1, y1); ctx.strokeRect(a, b, c - a, d - b); };
  rect(-L / 2, W / 2, L / 2, -W / 2);
  const line = (x0: number, y0: number, x1: number, y1: number) => { ctx.beginPath(); ctx.moveTo(...P(x0, y0)); ctx.lineTo(...P(x1, y1)); ctx.stroke(); };
  line(0, W / 2, 0, -W / 2);
  const [cx, cy] = P(0, 0);
  ctx.beginPath(); ctx.arc(cx, cy, 9.15 * s, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.arc(cx, cy, 2.5, 0, Math.PI * 2); ctx.fillStyle = "rgba(255,255,255,0.55)"; ctx.fill();
  for (const sd of [-1, 1]) {
    const gx = sd * L / 2;
    rect(gx, 20.16, gx - sd * 16.5, -20.16);
    rect(gx, 9.16, gx - sd * 5.5, -9.16);
    const [sx, sy] = P(gx - sd * 11, 0);
    ctx.beginPath(); ctx.arc(sx, sy, 2, 0, Math.PI * 2); ctx.fill();
    const a0 = sd < 0 ? -0.93 : Math.PI - 0.93;
    ctx.beginPath(); ctx.arc(sx, sy, 9.15 * s, a0, a0 + 1.86); ctx.stroke();
    ctx.strokeStyle = "rgba(255,255,255,0.8)"; ctx.lineWidth = 3;
    line(gx, 3.66, gx, -3.66);
    ctx.strokeStyle = "rgba(255,255,255,0.55)"; ctx.lineWidth = 1.4;
  }
}

function drawCourt(ctx: CanvasRenderingContext2D, P: Proj, L: number, W: number, s: number, w: number, h: number) {
  ctx.fillStyle = "#16110c"; ctx.fillRect(0, 0, w, h);
  const [a, b] = P(-L / 2, W / 2);
  const grd = ctx.createLinearGradient(a, 0, a + L * s, 0);
  grd.addColorStop(0, "#2a1f15"); grd.addColorStop(0.5, "#33261a"); grd.addColorStop(1, "#2a1f15");
  ctx.fillStyle = grd; ctx.fillRect(a, b, L * s, W * s);
  const FT = 0.3048;
  ctx.strokeStyle = "rgba(255,255,255,0.6)"; ctx.lineWidth = 1.4;
  ctx.strokeRect(a, b, L * s, W * s);
  const line = (x0: number, y0: number, x1: number, y1: number) => { ctx.beginPath(); ctx.moveTo(...P(x0, y0)); ctx.lineTo(...P(x1, y1)); ctx.stroke(); };
  line(0, W / 2, 0, -W / 2);
  const [cx, cy] = P(0, 0);
  ctx.beginPath(); ctx.arc(cx, cy, 6 * FT * s, 0, Math.PI * 2); ctx.stroke();
  for (const sd of [-1, 1]) {
    const bx = sd * (L / 2 - 5.25 * FT);        // basket centre 5.25 ft from baseline
    const lane = 16 * FT, laneLen = 19 * FT;
    const [lx0, ly0] = P(sd * L / 2, lane / 2), [lx1, ly1] = P(sd * (L / 2 - laneLen), -lane / 2);
    ctx.fillStyle = "rgba(251,146,60,0.10)";
    ctx.fillRect(Math.min(lx0, lx1), ly0, Math.abs(lx1 - lx0), ly1 - ly0);
    ctx.strokeRect(Math.min(lx0, lx1), ly0, Math.abs(lx1 - lx0), ly1 - ly0);
    const [fx, fy] = P(sd * (L / 2 - laneLen), 0);
    ctx.beginPath(); ctx.arc(fx, fy, 6 * FT * s, 0, Math.PI * 2); ctx.stroke();
    // three-point line: corners 22 ft from basket, arc 23.75 ft
    const r3 = 23.75 * FT, corner = 22 * FT;
    const cornerX = Math.sqrt(r3 * r3 - corner * corner);
    line(sd * L / 2, corner, bx - sd * cornerX, corner);
    line(sd * L / 2, -corner, bx - sd * cornerX, -corner);
    const [hx, hy] = P(bx, 0);
    const ang = Math.atan2(corner, cornerX);
    ctx.beginPath();
    if (sd > 0) ctx.arc(hx, hy, r3 * s, Math.PI - ang, Math.PI + ang);
    else ctx.arc(hx, hy, r3 * s, -ang, ang);
    ctx.stroke();
    ctx.strokeStyle = "#fb923c"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(hx, hy, 0.75 * FT * s, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = "rgba(255,255,255,0.6)"; ctx.lineWidth = 1.4;
    line(sd * (L / 2 - 4 * FT), 3 * FT, sd * (L / 2 - 4 * FT), -3 * FT);
  }
}

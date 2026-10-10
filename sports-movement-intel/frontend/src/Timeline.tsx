import { useMemo, useRef, useState } from "react";
import type { ChangePoint, MatchMeta, Moment } from "./api";
import { matchClock } from "./api";
import { COLORS } from "./geometry";

interface Props {
  meta: MatchMeta; playhead: number; cursor: number | null;
  windows: any[]; metric: string; changes: ChangePoint[]; moments: Moment[];
  onSeek: (t: number) => void;
}

const H = 118, TOP = 26, BAND = 56;
const LABEL: Record<string, string> = {
  width_m: "width", depth_m: "depth", hull_area_m2: "hull area", def_line_height_m: "defensive line", centroid_x: "centroid",
};

export function Timeline({ meta, playhead, cursor, windows, metric, changes, moments, onSeek }: Props) {
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<{ x: number; text: string } | null>(null);
  const [w, setW] = useState(1000);
  const total = Math.max(...meta.periods.map(p => p.offset_ms + p.duration_ms));
  const X = (t: number) => (t / total) * w;
  const home = meta.home_team.team_id;

  const series = useMemo(() => {
    const key = `mean_${metric}`;
    const byTeam: Record<string, { t: number; v: number }[]> = {};
    for (const r of windows) {
      if (r[key] === null || r[key] === undefined) continue;
      (byTeam[r.team_id] ??= []).push({ t: (r.window_start_ms + r.window_end_ms) / 2, v: r[key] });
    }
    const all = Object.values(byTeam).flat().map(p => p.v);
    const lo = Math.min(...all), hi = Math.max(...all);
    return { byTeam, lo, hi };
  }, [windows, metric]);

  const Y = (v: number) => TOP + BAND - ((v - series.lo) / (series.hi - series.lo || 1)) * (BAND - 6) - 3;
  const tFromEvent = (ev: React.MouseEvent) => {
    const b = ref.current!.getBoundingClientRect();
    return Math.max(0, Math.min(total, ((ev.clientX - b.left) / b.width) * total));
  };

  return (
    <div className="timeline" ref={el => { if (el && Math.abs(el.clientWidth - w) > 2) setW(el.clientWidth); }}>
      <svg ref={ref} width={w} height={H} onClick={ev => onSeek(tFromEvent(ev))}
        onMouseMove={ev => { const t = tFromEvent(ev); setHover({ x: X(t), text: matchClock(meta, t, periodAt(meta, t)) }); }}
        onMouseLeave={() => setHover(null)}>
        <defs>
          <linearGradient id="proc" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0.04" />
          </linearGradient>
        </defs>
        <rect x={0} y={TOP} width={w} height={BAND} rx={6} fill="#0f1524" />
        {cursor !== null && <rect x={0} y={TOP} width={X(Math.min(cursor, total))} height={BAND} rx={6} fill="url(#proc)" />}
        {meta.periods.map(p => (
          <g key={p.period}>
            <line x1={X(p.offset_ms)} x2={X(p.offset_ms)} y1={TOP - 4} y2={TOP + BAND + 4} stroke="#334155" />
            <text x={X(p.offset_ms) + 5} y={TOP - 8} className="tl-label">
              {meta.sport === "soccer" ? (p.period === 1 ? "1ST HALF" : "2ND HALF") : `Q${p.period}`}
            </text>
          </g>))}
        {Object.entries(series.byTeam).map(([tm, pts]) => (
          <polyline key={tm} fill="none" stroke={tm === home ? COLORS.home : COLORS.away} strokeWidth={1.6} strokeOpacity={0.9}
            points={pts.map(p => `${X(p.t)},${Y(p.v)}`).join(" ")} />))}
        {changes.map(c => (
          <g key={c.evidence_id} className="marker" onClick={ev => { ev.stopPropagation(); onSeek(c.t_ms); }}
            onMouseEnter={() => setHover({ x: X(c.t_ms), text: `${matchClock(meta, c.t_ms, c.period)} shape shift · ${c.top_features[0].feature} ${c.top_features[0].before.toFixed(1)}→${c.top_features[0].after.toFixed(1)}` })}>
            <line x1={X(c.t_ms)} x2={X(c.t_ms)} y1={TOP} y2={TOP + BAND} stroke={c.team_id === home ? COLORS.home : COLORS.away} strokeOpacity={0.35} strokeDasharray="2 3" />
            <path d={`M${X(c.t_ms) - 5},${c.team_id === home ? TOP - 1 : TOP + BAND + 1} l5,${c.team_id === home ? 7 : -7} l5,${c.team_id === home ? -7 : 7} z`}
              fill={c.team_id === home ? COLORS.home : COLORS.away} />
          </g>))}
        {moments.map(m => (
          <rect key={m.t_ms} x={X(m.t_ms) - 4} y={TOP + BAND / 2 - 4} width={8} height={8} transform={`rotate(45 ${X(m.t_ms)} ${TOP + BAND / 2})`}
            fill={COLORS.accent} stroke="#0b1020" className="marker" onClick={ev => { ev.stopPropagation(); onSeek(m.t_ms); }} />))}
        <line x1={X(playhead)} x2={X(playhead)} y1={TOP - 6} y2={TOP + BAND + 6} stroke="#fff" strokeWidth={2} />
        <circle cx={X(playhead)} cy={TOP - 6} r={4} fill="#fff" />
        {hover && <g pointerEvents="none">
          <line x1={hover.x} x2={hover.x} y1={TOP} y2={TOP + BAND} stroke="#94a3b8" strokeOpacity={0.5} />
          <text x={Math.min(hover.x + 6, w - 260)} y={TOP + BAND + 18} className="tl-hover">{hover.text}</text>
        </g>}
        <text x={w} y={TOP - 8} textAnchor="end" className="tl-label">{LABEL[metric] ?? metric} · 60 s windows · ▲▼ shape shifts · ◆ similar moments</text>
      </svg>
    </div>
  );
}

export function periodAt(meta: MatchMeta, t: number): number {
  let p = meta.periods[0]?.period ?? 1;
  for (const x of meta.periods) if (t >= x.offset_ms) p = x.period;
  return p;
}

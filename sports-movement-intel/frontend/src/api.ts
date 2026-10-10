export type Ent = [string, string, string, number, number, boolean, number]; // id,type,team,x,y,detected,speed(-1=null)
export interface Frame { seq: number; t: number; period: number; ents: Ent[] }

export interface Team { team_id: string; name: string; abbreviation?: string }
export interface PeriodMeta { period: number; offset_ms: number; duration_ms: number; attack_direction?: Record<string, number> }
export interface PlayerMeta { canonical_player_id: string; team_id: string; name?: string | null; jersey?: string | null; position?: string | null; is_goalkeeper?: boolean }

export interface MatchSummary {
  match_id: string; source: string; sport: "soccer" | "basketball";
  competition?: string; season?: string; date?: string;
  home_team: Team; away_team: Team;
  score?: { home: number; away: number } | null;
  dimensions: { length_m: number; width_m: number; physical: boolean };
  sample_rate_hz: number; capabilities: Record<string, unknown>;
  counts?: { frames: number; position_rows: number; events: number; players: number };
  periods: PeriodMeta[];
  quality: Record<string, unknown>; missing_segments: number;
  license?: string; attribution?: string; redistributable_demo: boolean;
}
export interface ScorePoint { t_ms: number; home: number; away: number }
export interface MatchMeta extends MatchSummary {
  players: PlayerMeta[];
  score_timeline?: ScorePoint[];
  score_source?: { source: string; license: string; attribution: string; placement: string };
}

/** Score at replay time t from a sorted score timeline (0–0 before the first scoring event). */
export function scoreAt(timeline: ScorePoint[], t: number): { home: number; away: number } {
  let lo = 0, hi = timeline.length - 1, best = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (timeline[mid].t_ms <= t) { best = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return best < 0 ? { home: 0, away: 0 } : timeline[best];
}

export interface Session {
  session_id: string; match_id: string; source: string; sport: string; speed: number; status: string;
  frames_sent: number; last_seq: number; started_at: string; updated_at: string; faults: string; note: string;
}

export interface ChangePoint {
  t_ms: number; period: number; team_id: string; magnitude_z: number;
  segment_before_ms: [number, number]; segment_after_ms: [number, number];
  top_features: { feature: string; delta: number; before: number; after: number }[]; evidence_id: string;
}
export interface Moment { t_ms: number; period: number; possession_label: string | null; distance?: number; similarity?: number; shape: Record<string, Record<string, number | null>> }

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}
const e = encodeURIComponent;
const post = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  catalog: () => j<{ badge: string; public_demo: boolean; matches: MatchSummary[] }>("/api/catalog"),
  match: (id: string) => j<MatchMeta>(`/api/matches/${e(id)}`),
  sessions: () => j<Session[]>(`/api/sessions?limit=100`),
  demo: () => j<any>("/api/demo"),
  start: (matchId: string, speed: number, faults: Record<string, number> = {}) =>
    j<{ session_id: string }>("/api/sessions", post({ match_id: matchId, speed, faults })),
  control: (sid: string, command: string, speed?: number) => j<any>(`/api/sessions/${e(sid)}/control`, post({ command, speed })),
  frames: (sid: string, mid: string, fromT: number, limit = 600) =>
    j<{ frames: Frame[] }>(`/api/sessions/${e(sid)}/frames?match_id=${e(mid)}&from_t=${Math.max(0, Math.floor(fromT))}&limit=${limit}`),
  cursor: (sid: string, mid: string) => j<any>(`/api/sessions/${e(sid)}/cursor?match_id=${e(mid)}`),
  heatmap: (sid: string, mid: string, q: Record<string, string | number | undefined>) => {
    const p = new URLSearchParams({ match_id: mid });
    Object.entries(q).forEach(([k, v]) => v !== undefined && v !== "" && p.set(k, String(v)));
    return j<any>(`/api/sessions/${e(sid)}/heatmap?${p}`);
  },
  players: (sid: string, mid: string) => j<any>(`/api/sessions/${e(sid)}/players?match_id=${e(mid)}`),
  teamMetrics: (sid: string, mid: string) => j<any>(`/api/sessions/${e(sid)}/team_metrics?match_id=${e(mid)}&step=50`),
  changes: (sid: string, mid: string) => j<{ changes: ChangePoint[]; note: string; model: string; version: string }>(`/api/sessions/${e(sid)}/changes?match_id=${e(mid)}`),
  similar: (sid: string, mid: string, t: number) => j<any>(`/api/sessions/${e(sid)}/similar?match_id=${e(mid)}&t_ms=${Math.floor(t)}`),
  lineage: (sid: string, mid: string) => j<any>(`/api/sessions/${e(sid)}/lineage?match_id=${e(mid)}`),
  health: (sid?: string) => j<any>(`/api/pipeline/health${sid ? `?session_id=${e(sid)}` : ""}`),
  ask: (body: unknown) => j<any>("/api/analyst/ask", post(body)),
};

export function fmtClock(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || ms < 0) return "--:--";
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Broadcast clock: soccer uses the conventional clock (period 2 starts at 45:00); NBA shows quarter + elapsed. */
export function matchClock(meta: MatchSummary, t: number, period: number): string {
  const p = meta.periods.find(x => x.period === period);
  const inPeriod = Math.max(0, t - (p?.offset_ms ?? 0));
  if (meta.sport === "soccer") return fmtClock(inPeriod + (period - 1) * 45 * 60000);
  return `Q${period} +${fmtClock(inPeriod)}`;   // sensor time since quarter start (includes stoppages)
}

export const fmt = (v: number | null | undefined, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? "–" : v.toFixed(d));
export const km = (m: number) => (m / 1000).toFixed(2);

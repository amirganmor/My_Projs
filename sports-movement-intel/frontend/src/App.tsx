import { useEffect, useMemo, useState } from "react";
import { api, type MatchMeta, type MatchSummary, type Session } from "./api";
import { CatalogView } from "./CatalogView";
import { LiveView } from "./LiveView";
import { PipelineView } from "./PipelineView";
import { PlayersView } from "./PlayersView";

type View = "live" | "players" | "pipeline" | "catalog";
const VIEWS: { k: View; label: string }[] = [
  { k: "live", label: "Live" }, { k: "players", label: "Players" }, { k: "pipeline", label: "Pipeline" }, { k: "catalog", label: "Catalog" },
];
const DEMO_LABEL: Record<string, string> = {
  "demo-soccer-hero": "Hero · SkillCorner A-League · 20×",
  "demo-soccer-faults": "Faults · SkillCorner · injected delivery faults",
  "demo-nba": "NBA · SportVU 2015-16 (local only)",
};

const params = new URLSearchParams(window.location.search);

export function App() {
  const [view, setView] = useState<View>((params.get("view") as View) || "live");
  const [catalog, setCatalog] = useState<{ matches: MatchSummary[]; public_demo: boolean } | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [demo, setDemo] = useState<any>(null);
  const [sid, setSid] = useState<string | null>(params.get("session"));
  const [meta, setMeta] = useState<MatchMeta | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [launch, setLaunch] = useState(false);

  const refresh = () => Promise.all([api.catalog(), api.sessions(), api.demo()])
    .then(([c, s, d]) => { setCatalog(c); setSessions(s); setDemo(d); })
    .catch(e => setErr(String(e)));
  useEffect(() => { refresh(); const id = setInterval(() => api.sessions().then(setSessions).catch(() => {}), 5000); return () => clearInterval(id); }, []);

  const ordered = useMemo(() => {
    const demoIds = Object.keys(DEMO_LABEL);
    return [...sessions].sort((a, b) => {
      const da = demoIds.indexOf(a.session_id), db = demoIds.indexOf(b.session_id);
      if (da !== db) return (da < 0 ? 99 : da) - (db < 0 ? 99 : db);
      return b.updated_at.localeCompare(a.updated_at);
    });
  }, [sessions]);

  useEffect(() => { if (!sid && ordered.length) setSid(ordered[0].session_id); }, [ordered, sid]);
  const session = ordered.find(s => s.session_id === sid) ?? null;
  useEffect(() => {
    if (!session) return;
    if (meta?.match_id === session.match_id && meta.license !== undefined) return;
    setMeta(null);
    const summary = catalog?.matches.find(m => m.match_id === session.match_id);
    api.match(session.match_id).then(m => setMeta({ ...m, ...(summary ?? {}), players: m.players })).catch(e => setErr(String(e)));
  }, [session?.match_id, catalog]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo"><span /><span /><span /></div>
          <div>
            <div className="brand-name">Sports Movement Intelligence</div>
            <div className="brand-sub">Kafka · Spark Structured Streaming · Iceberg · ClickHouse</div>
          </div>
        </div>
        <nav>{VIEWS.map(v => <button key={v.k} className={view === v.k ? "on" : ""} onClick={() => setView(v.k)}>{v.label}</button>)}</nav>
        <div className="session-pick">
          <select value={sid ?? ""} onChange={e => setSid(e.target.value)}>
            {ordered.map(s => <option key={s.session_id} value={s.session_id}>{DEMO_LABEL[s.session_id] ?? `${s.session_id} · ${s.status}`}</option>)}
          </select>
          <button className="ghost" onClick={() => setLaunch(l => !l)}>+ replay</button>
          {catalog?.public_demo && <span className="badge ok">public demo</span>}
        </div>
      </header>
      {launch && catalog && <Launcher matches={catalog.matches} onStarted={id => { setLaunch(false); refresh().then(() => setSid(id)); setView("live"); }} />}
      {err && <div className="err banner">{err}</div>}
      <main>
        {view === "catalog" && catalog && <CatalogView matches={catalog.matches} sessions={sessions} publicDemo={catalog.public_demo}
          onOpen={s => { setSid(s.session_id); setView("live"); }} />}
        {view !== "catalog" && !session && <Empty />}
        {view !== "catalog" && session && meta && meta.match_id === session.match_id && (
          <>
            {view === "live" && <LiveView key={session.session_id} session={session} meta={meta} />}
            {view === "players" && <PlayersView session={session} meta={meta} />}
            {view === "pipeline" && <PipelineView session={session} meta={meta} demo={demo} />}
          </>)}
      </main>
      <footer>
        Historical match replay of public tracking data · SkillCorner open data (MIT) · Metrica and SportVU are local-only · no live feeds, no betting
      </footer>
    </div>
  );
}

function Empty() {
  return (
    <div className="empty">
      <h2>No replay sessions yet</h2>
      <p>Run <span className="mono">make demo-seed</span> to replay the demo matches through Kafka and Spark, or start one with <b>+ replay</b>.</p>
    </div>
  );
}

function Launcher({ matches, onStarted }: { matches: MatchSummary[]; onStarted: (sid: string) => void }) {
  const [mid, setMid] = useState(matches[0]?.match_id ?? "");
  const [speed, setSpeed] = useState(20);
  const [faults, setFaults] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const start = async () => {
    setBusy(true); setErr(null);
    try {
      const f: Record<string, number> = faults ? { duplicate_rate: 0.03, out_of_order_rate: 0.02, delay_rate: 0.01, correction_rate: 0.01, malformed_rate: 0.002 } : {};
      const r = await api.start(mid, speed, f);
      onStarted(r.session_id);
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  return (
    <div className="launcher">
      <select value={mid} onChange={e => setMid(e.target.value)}>
        {matches.map(m => <option key={m.match_id} value={m.match_id}>{m.home_team.name} vs {m.away_team.name} ({m.source})</option>)}
      </select>
      <div className="seg">{[1, 5, 20, 50].map(s => <button key={s} className={speed === s ? "on" : ""} onClick={() => setSpeed(s)}>{s}×</button>)}</div>
      <label className="check"><input type="checkbox" checked={faults} onChange={e => setFaults(e.target.checked)} /> inject delivery faults</label>
      <button onClick={start} disabled={busy}>{busy ? "starting…" : "Start historical replay"}</button>
      {err && <span className="err">{err}</span>}
    </div>
  );
}

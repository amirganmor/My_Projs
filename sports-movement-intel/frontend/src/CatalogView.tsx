import type { MatchSummary, Session } from "./api";

const CAP_LABEL: Record<string, string> = {
  continuous_tracking: "tracking", ball: "ball", ball_height: "ball height", events: "events", phases: "phases",
  detection_flag: "detection flag", identity: "identity", possession: "possession",
};

export function CatalogView({ matches, sessions, publicDemo, onOpen }: {
  matches: MatchSummary[]; sessions: Session[]; publicDemo: boolean; onOpen: (s: Session) => void;
}) {
  return (
    <div className="catalog-view">
      <div className="view-h">
        <div>
          <h2>Data catalog</h2>
          <div className="muted">Normalized historical matches. Licenses come from each dataset's own terms, never from a downloader's software license.
            {publicDemo && " Public demo mode: only redistributable (MIT) data is listed."}</div>
        </div>
      </div>
      <div className="cards">
        {matches.map(m => {
          const q = m.quality as any;
          const ss = sessions.filter(s => s.match_id === m.match_id);
          return (
            <div key={m.match_id} className={`card ${m.sport}`}>
              <div className="card-top">
                <span className={`sport ${m.sport}`}>{m.sport === "soccer" ? "⚽ Soccer" : "🏀 Basketball"}</span>
                <span className={m.redistributable_demo ? "badge ok" : "badge warn"}>{m.redistributable_demo ? "redistributable" : "local only"}</span>
              </div>
              <div className="card-title">{m.home_team.name} <span className="muted">vs</span> {m.away_team.name}</div>
              <div className="muted">{m.competition} · {m.season} · {m.date?.slice(0, 10)}{m.score ? ` · ${m.score.home}–${m.score.away}` : ""}</div>
              <div className="kv">
                <div><span>source</span><b>{m.source}</b></div>
                <div><span>frames</span><b>{m.counts?.frames?.toLocaleString("en-US") ?? "–"} @ {m.sample_rate_hz} Hz</b></div>
                <div><span>positions</span><b>{m.counts?.position_rows?.toLocaleString("en-US") ?? "–"}</b></div>
                <div><span>detected</span><b>{q?.detected_fraction != null ? `${Math.round(q.detected_fraction * 100)}%` : "not provided"}</b></div>
                <div><span>gaps &gt; 5 s</span><b>{m.missing_segments}</b></div>
                <div><span>surface</span><b>{m.dimensions.length_m.toFixed(1)} × {m.dimensions.width_m.toFixed(1)} m</b></div>
                <div><span>match id</span><b className="mono">{m.match_id}</b></div>
              </div>
              <div className="license"><span>data license</span>{m.license ?? "unresolved"}</div>
              <div className="caps">
                {Object.entries(m.capabilities).map(([k, v]) => (
                  <span key={k} className={v === false || v === "none" ? "cap off" : "cap"} title={String(v)}>{CAP_LABEL[k] ?? k}{typeof v === "string" ? `: ${v.split(" ")[0]}` : ""}</span>))}
              </div>
              {m.attribution && <div className="muted small attribution">{m.attribution}</div>}
              <div className="card-sessions">
                {ss.slice(0, 3).map(s => <button key={s.session_id} className="chip" onClick={() => onOpen(s)}>open {s.session_id}</button>)}
                {!ss.length && <span className="muted small">no replay sessions yet</span>}
              </div>
            </div>);
        })}
      </div>
    </div>
  );
}

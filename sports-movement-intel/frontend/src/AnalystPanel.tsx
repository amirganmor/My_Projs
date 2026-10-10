import { useEffect, useState } from "react";
import { api, matchClock, type MatchMeta } from "./api";
import { periodAt } from "./Timeline";

const EXAMPLES: Record<string, string[]> = {
  soccer: [
    "Which players covered the most distance?",
    "How high was the defensive line over time?",
    "What changed in team shape so far?",
    "Which parts of this match have insufficient tracking quality?",
    "Show moments similar to this one",
  ],
  basketball: [
    "Who had the highest max speed?",
    "How did team spread change over time?",
    "What changed in team shape so far?",
    "Which parts of this game have tracking gaps?",
  ],
};

export function AnalystPanel({ sid, meta, playhead, onJump, initial }: {
  sid: string; meta: MatchMeta; playhead: number; onJump: (t: number) => void; initial?: string | null;
}) {
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<"replay_time" | "post_match">("replay_time");
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const ask = async (question: string) => {
    setQ(question); setBusy(true); setErr(null);
    try {
      setRes(await api.ask({ question, match_id: meta.match_id, session_id: sid, mode,
        as_of_ms: mode === "replay_time" ? Math.floor(playhead) : undefined }));
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };

  useEffect(() => { if (initial) { const id = setTimeout(() => ask(initial), 1500); return () => clearTimeout(id); } }, []);

  return (
    <div className="panel analyst">
      <div className="panel-h">
        <h3>Grounded analyst</h3>
        <div className="seg small-seg">
          <button className={mode === "replay_time" ? "on" : ""} onClick={() => setMode("replay_time")} title="never reads past the playhead">as of {matchClock(meta, playhead, periodAt(meta, playhead))}</button>
          <button className={mode === "post_match" ? "on" : ""} onClick={() => setMode("post_match")}>full match</button>
        </div>
      </div>
      <form onSubmit={ev => { ev.preventDefault(); q.trim() && ask(q); }} className="ask">
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Ask about shape, players, quality…" maxLength={500} />
        <button disabled={busy}>{busy ? "…" : "Ask"}</button>
      </form>
      <div className="chips">
        {EXAMPLES[meta.sport].map(x => <button key={x} className="chip" onClick={() => ask(x)}>{x}</button>)}
      </div>
      {err && <div className="err">{err}</div>}
      {res && (
        <div className="answer">
          {res.refused ? (
            <div className="refused"><b>Not answered.</b> {res.refusal_reason}
              {res.supported && <ul>{res.supported.map((s: string) => <li key={s}>{s}</li>)}</ul>}
            </div>
          ) : (
            <>
              <div className="answer-h">{res.answer}</div>
              <ol>
                {res.observations.map((o: any, i: number) => (
                  <li key={i}>
                    <span>{o.statement}</span>
                    {o.evidence_ids.map((e: string) => {
                      const m = /t=(\d+)/.exec(e);
                      return <button key={e} className="evidence" title={e} onClick={() => m && onJump(Number(m[1]))}>
                        {m ? `⏵ ${matchClock(meta, Number(m[1]), periodAt(meta, Number(m[1])))}` : e.split(":")[0]}</button>;
                    })}
                  </li>))}
              </ol>
            </>
          )}
          <div className="answer-foot">
            tool <b>{res.tools_called?.[0]?.tool ?? "none"}</b> · {res.method} · generator {res.generator} · {res.latency_ms} ms
            {res.time_range?.[1] != null && <> · cutoff {matchClock(meta, res.time_range[1], periodAt(meta, res.time_range[1]))}</>}
            {res.limitations?.length > 0 && <div className="muted">{res.limitations.join(" · ")}</div>}
          </div>
        </div>
      )}
    </div>
  );
}

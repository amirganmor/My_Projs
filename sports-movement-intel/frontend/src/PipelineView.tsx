import { useEffect, useState } from "react";
import { api, type MatchMeta, type Session } from "./api";

const n = (v: any) => (v == null ? "–" : Number(v).toLocaleString("en-US"));

export function PipelineView({ session, meta, demo }: { session: Session; meta: MatchMeta; demo: any }) {
  const sid = session.session_id, mid = meta.match_id;
  const [health, setHealth] = useState<any>(null);
  const [lineage, setLineage] = useState<any>(null);
  const [linErr, setLinErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const load = () => api.health(sid).then(h => live && setHealth(h)).catch(() => {});
    load(); const id = setInterval(load, 3000);
    return () => { live = false; clearInterval(id); };
  }, [sid]);
  useEffect(() => {
    setLineage(null); setLinErr(null);
    api.lineage(sid, mid).then(setLineage).catch(e => setLinErr(String(e)));
  }, [sid, mid]);

  const s = health?.sessions?.[0];
  const eng = s?.engine ?? {};
  const c = eng.counters ?? Object.fromEntries(Object.entries(eng).filter(([k]) => k.startsWith("c_")).map(([k, v]) => [k.slice(2), v]));
  const demoEntry = demo?.sessions?.find((d: any) => d.session_id === sid);
  const parity = demoEntry?.parity;
  const quarantined = (s?.quarantine ?? []).reduce((a: number, q: any) => a + q.n, 0);
  const L = lineage ?? {};
  const gold = (k: string) => L[k]?.rows;

  const stages = [
    { title: "Historical replay", sub: `${meta.source} · ${session.speed ? `${session.speed}×` : "unthrottled"}`, stats: [["frames sent", n(s?.frames_sent)], ["status", s?.status ?? "–"]] },
    { title: "Kafka (KRaft)", sub: "smip.tracking.v1 · key session|match", stats: [["offsets", L.bronze?.kafka_offsets ? `${n(L.bronze.kafka_offsets[0])}–${n(L.bronze.kafka_offsets[1])}` : "–"], ["partition", L.bronze?.kafka_partitions?.join(", ") ?? "–"]] },
    { title: "Spark · bronze", sub: "validate · quarantine", stats: [["records", n(L.bronze?.records)], ["quarantined", n(quarantined)]] },
    { title: "Spark · engine", sub: "applyInPandasWithState", stats: [["duplicates", n(c.duplicate)], ["cross-batch reorders", n(c.reordered)], ["corrections", n(c.corrections_applied)], ["late", n((c.late_beyond_reorder_buffer ?? 0) + (c.late_correction ?? 0))]] },
    { title: "Iceberg (REST)", sub: "./lakehouse · silver + gold", stats: [["silver frames", n(L["silver.tracking_frames"]?.rows)], ["positions", n(L["silver.tracking_positions"]?.rows)], ["player windows", n(gold("gold.player_windows"))], ["dwell cells", n(gold("gold.spatial_dwell"))]] },
    { title: "ClickHouse", sub: "ReplacingMergeTree · FINAL", stats: [["frames", n(s?.processed?.frames)], ["p50 latency", s?.processed?.p50_ms != null ? `${n(s.processed.p50_ms)} ms` : "–"], ["p95 latency", s?.processed?.p95_ms != null ? `${n(s.processed.p95_ms)} ms` : "–"]] },
    { title: "API · UI", sub: "FastAPI · this dashboard", stats: [["cursor", eng.cursor_t != null ? `${Math.round(eng.cursor_t / 1000)} s` : "–"], ["reorder buffer", n(eng.buffer_size)]] },
  ];

  return (
    <div className="pipeline-view">
      <div className="view-h">
        <div>
          <h2>Pipeline</h2>
          <div className="muted">Every number on the Live view is read from these stages. Session <span className="mono">{sid}</span></div>
        </div>
        <div className="badges">
          {parity && <span className={parity.ok ? "badge ok" : "badge bad"}>{parity.ok ? "✓ batch = stream parity" : "✗ parity mismatch"}</span>}
          {lineage && <span className={lineage["silver.tracking_frames"]?.rows === meta.counts?.frames ? "badge ok" : "badge warn"}>
            {lineage["silver.tracking_frames"]?.rows === meta.counts?.frames ? "✓ lineage complete" : "lineage partial"}</span>}
          <span className="badge replay">● HISTORICAL MATCH REPLAY</span>
        </div>
      </div>

      {!session.speed && <div className="note">Unthrottled replay: the whole match is produced in seconds, so produce→ClickHouse latency here is backlog queueing, not steady-state latency. See the 20× hero session and docs/BENCHMARKS.md.</div>}
      <div className="flow">
        {stages.map((st, i) => (
          <div key={st.title} className="flow-step">
            <div className="flow-card">
              <div className="flow-title">{st.title}</div>
              <div className="flow-sub">{st.sub}</div>
              {st.stats.map(([k, v]) => <div key={k} className="flow-stat"><span>{k}</span><b>{v}</b></div>)}
            </div>
            {i < stages.length - 1 && <div className="flow-arrow"><i /></div>}
          </div>))}
      </div>

      <div className="pv-grid">
        <div className="panel">
          <div className="panel-h"><h3>Batch vs stream parity</h3><span className="muted">same engine over normalized parquet vs Kafka → Spark output</span></div>
          {parity ? (
            <table className="mini">
              <thead><tr><th>table</th><th>batch rows</th><th>stream rows</th><th>only batch</th><th>only stream</th><th>value mismatches</th><th /></tr></thead>
              <tbody>{Object.entries(parity.tables).map(([t, r]: any) => (
                <tr key={t}><td className="mono">{t}</td><td>{n(r.batch_rows)}</td><td>{n(r.stream_rows)}</td><td>{r.only_batch}</td><td>{r.only_stream}</td>
                  <td>{Object.keys(r.mismatched_values).length}</td><td>{r.pass ? <span className="ok-t">pass</span> : <span className="bad-t">fail</span>}</td></tr>))}
              </tbody>
            </table>) : <div className="muted small">No parity report for this session (run <span className="mono">smip batch parity</span>).</div>}
        </div>

        <div className="panel">
          <div className="panel-h"><h3>Iceberg lineage</h3><span className="muted">row counts for this session per table</span></div>
          {linErr && <div className="err">{linErr}</div>}
          {!lineage && !linErr && <div className="muted small">scanning Iceberg tables…</div>}
          {lineage && (
            <table className="mini">
              <thead><tr><th>table</th><th>rows</th><th>final</th><th>engine batches</th><th>feature version</th></tr></thead>
              <tbody>
                <tr><td className="mono">bronze.kafka_tracking_raw</td><td>{n(lineage.bronze.records)}</td><td>{n(lineage.bronze.valid)} valid</td><td>–</td><td>–</td></tr>
                {["silver.tracking_frames", "silver.tracking_positions", "gold.team_frame_metrics", "gold.player_windows", "gold.team_windows", "gold.spatial_dwell"].map(t => (
                  <tr key={t}><td className="mono">{t}</td><td>{n(lineage[t]?.rows)}</td><td>{n(lineage[t]?.final_rows)}</td><td>{n(lineage[t]?.engine_batches)}</td><td className="mono small">{lineage[t]?.feature_version?.join(", ") ?? "–"}</td></tr>))}
              </tbody>
            </table>)}
        </div>

        <div className="panel">
          <div className="panel-h"><h3>Delivery faults</h3><span className="muted">seeded, bounded injection in the replay producer</span></div>
          <FaultTable faults={session.faults} counters={c} quarantine={s?.quarantine ?? []} />
        </div>

        <div className="panel">
          <div className="panel-h"><h3>Sinks</h3><span className="muted">{health?.semantics}</span></div>
          <table className="mini">
            <thead><tr><th>query</th><th>batches</th><th>rows</th><th>avg batch ms</th></tr></thead>
            <tbody>{(health?.sinks ?? []).map((r: any) => <tr key={r.query_name}><td className="mono">{r.query_name}</td><td>{n(r.batches)}</td><td>{n(r.rows)}</td><td>{n(Math.round(r.avg_batch_ms))}</td></tr>)}</tbody>
          </table>
          <div className="muted small">Iceberg commits carry a <span className="mono">smip.commit=query:batch</span> snapshot tag; a retried batch finds its tag and skips. ClickHouse is at-least-once with ReplacingMergeTree + FINAL reads. No global exactly-once claim.</div>
        </div>
      </div>
    </div>
  );
}

function FaultTable({ faults, counters, quarantine }: { faults: string; counters: any; quarantine: any[] }) {
  let f: Record<string, number> = {};
  try { f = JSON.parse(faults || "{}"); } catch { /* registry row may be partial */ }
  const rows = [
    ["duplicate_rate", "duplicates dropped", counters.duplicate],
    ["out_of_order_rate", "reordered across micro-batches (in-batch order is sorted)", counters.reordered],
    ["delay_rate", "late beyond buffer", counters.late_beyond_reorder_buffer ?? 0],
    ["correction_rate", "corrections applied", counters.corrections_applied],
    ["malformed_rate", "quarantined", quarantine.reduce((a, q) => a + q.n, 0)],
  ];
  return (
    <table className="mini">
      <thead><tr><th>injected</th><th>rate</th><th>observed outcome</th><th>count</th></tr></thead>
      <tbody>{rows.map(([k, label, v]) => (
        <tr key={k as string}><td className="mono">{(k as string).replace("_rate", "")}</td><td>{f[k as string] ? `${((f[k as string] as number) * 100).toFixed(1)}%` : "off"}</td><td>{label}</td><td>{v == null ? "–" : Number(v).toLocaleString("en-US")}</td></tr>))}
      </tbody>
    </table>
  );
}

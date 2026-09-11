import type { ToolManifestEntry } from "../api";
import type { TraceRow } from "../selectors";

export type TraceViewProps = { rows: TraceRow[]; tools: ToolManifestEntry[] };

export function TraceView({ rows, tools }: TraceViewProps) {
  return (
    <div className="ss-card">
      <h3 data-beat="trace-title">Trace — scores next to the actions they produced</h3>
      <details>
        <summary>Tools ({tools.length})</summary>
        <ul>
          {tools.map((t) => (
            <li key={t.name}>
              <code>{t.name}</code> — {t.description}
              <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(t.input_schema)}</pre>
            </li>
          ))}
        </ul>
      </details>
      <table className="ss-trace">
        <thead>
          <tr>
            <th>frame</th>
            <th>s</th>
            <th>score</th>
            <th>conf</th>
            <th>thr</th>
            <th>action</th>
            <th>reason</th>
            <th>human</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.sequence} className={r.action === "request_pause_approval" ? "ss-alert" : ""}>
              <td>{r.frameIndex}</td>
              <td>{(r.tMs / 1000).toFixed(1)}</td>
              <td>{r.spaghettiScore.toFixed(2)}</td>
              <td>{r.confidence.toFixed(2)}</td>
              <td>{r.threshold.toFixed(2)}</td>
              <td>{r.action}</td>
              <td>{r.reasonCode}</td>
              <td>{r.requiresHuman ? "yes" : "no"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

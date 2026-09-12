import type { JSX } from "react";
import type { ToolManifestEntry } from "../api";
import type { TraceRow } from "../selectors";

export type TraceViewProps = { rows: TraceRow[]; tools: ToolManifestEntry[] };

export function TraceView({ rows, tools }: TraceViewProps): JSX.Element {
  return (
    <section aria-label="Decision trace" className="card">
      <span className="caption">Decision trace</span>
      <details className="tools-details">
        <summary>Agent tools ({tools.length})</summary>
        <ul>
          {tools.map((t) => (
            <li key={t.name}>
              <span className="mono">{t.name}</span> — {t.description}{" "}
              <span className="mono muted">→ {t.output_key}</span>
              <pre className="mono muted">{JSON.stringify(t.input_schema)}</pre>
            </li>
          ))}
        </ul>
      </details>
      {rows.length === 0 ? (
        <p className="small muted" role="status">
          The trace fills in as frames are scored and decisions are made.
        </p>
      ) : (
        <div className="trace-scroll">
          <table className="ss-trace">
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">t (ms)</th>
                <th scope="col">frame</th>
                <th scope="col">spaghetti</th>
                <th scope="col">confidence</th>
                <th scope="col">threshold</th>
                <th scope="col">action</th>
                <th scope="col">reason</th>
                <th scope="col">human?</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const alert = r.action === "request_pause_approval";
                return (
                  <tr key={r.sequence} className={alert ? "row-alert" : r.degraded ? "row-degraded" : undefined}>
                    <td>{r.sequence}</td>
                    <td className="readout">{Math.round(r.tMs)}</td>
                    <td className="readout">{r.frameIndex}</td>
                    <td className="readout">{r.spaghettiScore.toFixed(2)}</td>
                    <td className="readout">{r.confidence.toFixed(2)}</td>
                    <td className="readout">{r.threshold.toFixed(2)}</td>
                    <td>{r.action}</td>
                    <td className="mono">{r.reasonCode}</td>
                    <td>{r.requiresHuman ? "yes" : "no"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

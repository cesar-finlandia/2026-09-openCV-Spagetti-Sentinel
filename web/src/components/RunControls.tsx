import { useRef, useState, type JSX } from "react";
import type { FixtureClip, StartRunRequest } from "../api";

export type RunControlsProps = {
  fixtures: FixtureClip[];
  disabled: boolean;
  busy: boolean;
  error: string | null;
  collapsible: boolean;
  onStart: (req: StartRunRequest) => void;
  onUpload: (file: File) => void;
};

export function RunControls({ fixtures, disabled, busy, error, collapsible, onStart, onUpload }: RunControlsProps): JSX.Element {
  const [fixtureId, setFixtureId] = useState("");
  const [backend, setBackend] = useState<"cool" | "baseline">("baseline");
  const [replay, setReplay] = useState(true);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const body = (
    <>
      <div className="field">
        <label className="caption" htmlFor="run-fixture">
          Demo clip
        </label>
        <select
          id="run-fixture"
          value={fixtureId}
          disabled={disabled || busy}
          onChange={(e) => setFixtureId(e.target.value)}
        >
          <option value="">first available clip</option>
          {fixtures.map((f) => (
            <option key={f.id} value={f.id}>
              {f.id} — {f.label}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label className="caption" htmlFor="run-backend">
          OpenCV backend
        </label>
        <select
          id="run-backend"
          value={backend}
          disabled={disabled || busy}
          onChange={(e) => setBackend(e.target.value === "cool" ? "cool" : "baseline")}
        >
          <option value="baseline">baseline</option>
          <option value="cool">cool</option>
        </select>
      </div>
      <div className="field">
        <label className="checkbox-row" htmlFor="run-replay">
          <input
            id="run-replay"
            type="checkbox"
            checked={replay}
            disabled={disabled || busy}
            onChange={(e) => setReplay(e.target.checked)}
          />
          <span>
            Replay (offline)
            <br />
            <span className="helper">Runs from cached frames — no AWS, no network.</span>
          </span>
        </label>
      </div>
      <div className="btn-row" style={{ display: "flex", gap: "var(--sp-3)", flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn btn-primary"
          disabled={disabled || busy}
          onClick={() => onStart({ fixture_id: fixtureId || undefined, backend, replay })}
        >
          {busy ? (
            <>
              <span className="spinner" aria-hidden="true" />
              Starting…
            </>
          ) : (
            "Start watching"
          )}
        </button>
        <button
          type="button"
          className="btn btn-outline"
          disabled={disabled || busy}
          onClick={() => fileRef.current?.click()}
        >
          Upload your own clip
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="video/*"
          aria-label="Upload your own clip"
          style={{ display: "none" }}
          disabled={disabled || busy}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onUpload(f);
            e.target.value = "";
          }}
        />
      </div>
      {error ? (
        <p className="error-line" role="alert">
          Could not start the run — {error}. Press &ldquo;Start watching&rdquo; to try again.
        </p>
      ) : null}
    </>
  );

  const card = (
    <section aria-label="Start a run" className={error ? "card control--error" : "card"}>
      <span className="caption">Start a run</span>
      {body}
    </section>
  );

  if (collapsible) {
    return (
      <details open={!disabled} className={error ? "control--error" : undefined}>
        <summary>Start a run</summary>
        {body}
      </details>
    );
  }
  return card;
}

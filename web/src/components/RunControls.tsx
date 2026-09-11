import { useState } from "react";
import type { FixtureClip, StartRunRequest } from "../api";

export type RunControlsProps = {
  fixtures: FixtureClip[];
  disabled: boolean;
  onStart: (req: StartRunRequest) => void;
  onUpload: (file: File) => void;
};

export function RunControls(props: RunControlsProps) {
  const { fixtures, disabled, onStart, onUpload } = props;
  const [fixtureId, setFixtureId] = useState("spaghetti");
  const [backend, setBackend] = useState<"cool" | "baseline">("cool");
  const [replay, setReplay] = useState(false);
  const [sampleN, setSampleN] = useState(3);

  return (
    <div className="ss-card">
      <div className="ss-row">
        <label>
          Fixture{" "}
          <select
            data-beat="fixture-select"
            value={fixtureId}
            disabled={disabled}
            onChange={(e) => setFixtureId(e.target.value)}
          >
            {fixtures.map((f) => (
              <option key={f.id} value={f.id}>
                {f.id} ({f.label})
              </option>
            ))}
          </select>
        </label>
        <label>
          Backend{" "}
          <select
            value={backend}
            disabled={disabled}
            onChange={(e) => setBackend(e.target.value as "cool" | "baseline")}
          >
            <option value="cool">cool</option>
            <option value="baseline">baseline</option>
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={replay}
            disabled={disabled}
            onChange={(e) => setReplay(e.target.checked)}
          />{" "}
          Replay (offline)
        </label>
        <label>
          Every Nth{" "}
          <input
            type="number"
            min={1}
            max={30}
            value={sampleN}
            disabled={disabled}
            onChange={(e) => setSampleN(Number(e.target.value))}
            style={{ width: 56 }}
          />
        </label>
        <button
          className="ss-btn ss-btn--primary"
          disabled={disabled}
          onClick={() =>
            onStart({ fixture_id: fixtureId, backend, replay, sample_every_n: sampleN })
          }
        >
          Start
        </button>
        <label className="ss-muted">
          or upload{" "}
          <input
            type="file"
            accept="video/*"
            disabled={disabled}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUpload(f);
            }}
          />
        </label>
      </div>
    </div>
  );
}

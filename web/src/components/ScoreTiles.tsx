import { useEffect, useRef, useState, type JSX } from "react";
import type { VisionScores } from "../selectors";

export type ScoreTilesProps = {
  latest: VisionScores | null;
  previous: VisionScores | null;
  threshold: number;
};

function Tile({
  label,
  value,
  delta,
  above,
}: {
  label: string;
  value: string;
  delta: string;
  above: boolean | null;
}): JSX.Element {
  const [ticked, setTicked] = useState(false);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    setTicked(true);
    const id = window.setTimeout(() => setTicked(false), 200);
    return () => window.clearTimeout(id);
  }, [value]);
  const cls = above === null ? "score-tile" : above ? "score-tile above" : "score-tile below";
  return (
    <div className={cls}>
      <span className="caption">{label}</span>
      <div className={ticked ? "readout-lg ticked readout" : "readout-lg"} aria-live="off">
        {value}
      </div>
      <div className="small muted">{delta}</div>
    </div>
  );
}

export function ScoreTiles({ latest, previous, threshold }: ScoreTilesProps): JSX.Element {
  if (latest === null) {
    return (
      <div className="score-tiles" role="status" aria-label="scores not yet available">
        <div className="score-tile">
          <span className="caption">Spaghetti score</span>
          <div className="readout-lg" aria-hidden="true">
            —
          </div>
          <div className="small muted">waiting for the first frame</div>
        </div>
        <div className="score-tile">
          <span className="caption">Confidence</span>
          <div className="readout-lg" aria-hidden="true">
            —
          </div>
          <div className="small muted">waiting for the first frame</div>
        </div>
      </div>
    );
  }
  const dScore = previous ? latest.spaghetti_score - previous.spaghetti_score : 0;
  const dConf = previous ? latest.confidence - previous.confidence : 0;
  const fmt = (d: number) => `${d >= 0 ? "+" : ""}${d.toFixed(2)} since frame ${previous ? previous.frame_index : latest.frame_index}`;
  return (
    <div className="score-tiles">
      <Tile
        label="Spaghetti score"
        value={latest.spaghetti_score.toFixed(2)}
        delta={previous ? fmt(dScore) : `frame ${latest.frame_index}`}
        above={latest.spaghetti_score >= threshold}
      />
      <Tile
        label="Confidence"
        value={latest.confidence.toFixed(2)}
        delta={previous ? fmt(dConf) : `frame ${latest.frame_index}`}
        above={null}
      />
    </div>
  );
}

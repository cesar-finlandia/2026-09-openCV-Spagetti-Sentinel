import { useEffect, useRef, useState, type JSX } from "react";
import type { VisionScores } from "../selectors";

export type ScoreTilesProps = {
  latest: VisionScores | null;
  previous: VisionScores | null;
  threshold: number;
};

/**
 * DP-UI-V2 §6: a value that counts up is legible motion; an instant DOM swap is
 * invisible at 30 fps. 240 ms, the --motion-base window, honouring reduced motion.
 */
function useCountUp(target: number | null, ms = 240): number | null {
  const [shown, setShown] = useState<number | null>(target);
  const from = useRef<number | null>(target);
  useEffect(() => {
    if (target === null) {
      setShown(null);
      from.current = null;
      return;
    }
    const start = from.current;
    from.current = target;
    const reduce =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (start === null || reduce || start === target) {
      setShown(target);
      return;
    }
    const t0 = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / ms);
      const eased = 1 - Math.pow(1 - p, 3);
      setShown(start + (target - start) * eased);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return shown;
}

/**
 * The hero metric. ui-craft §13.1: the route's hero metric is >= 64px — this one
 * is 72px — and §13.2: exactly one element per route carries data-demo-focus.
 */
function Hero({
  value,
  above,
  caption,
}: {
  value: number | null;
  above: boolean;
  caption: string;
}): JSX.Element {
  const shown = useCountUp(value);
  return (
    <div
      className={above ? "score-tile hero-metric above" : "score-tile hero-metric"}
      data-demo-focus="score"
    >
      <span className="caption">Spaghetti score</span>
      <div className="hero" aria-live="off">
        {shown === null ? "—" : shown.toFixed(2)}
      </div>
      <div className="small muted">{caption}</div>
    </div>
  );
}

function Tile({ label, value, delta }: { label: string; value: number | null; delta: string }): JSX.Element {
  const shown = useCountUp(value);
  return (
    <div className="score-tile">
      <span className="caption">{label}</span>
      <div className="readout-lg" aria-live="off">
        {shown === null ? "—" : shown.toFixed(2)}
      </div>
      <div className="small muted">{delta}</div>
    </div>
  );
}

export function ScoreTiles({ latest, previous, threshold }: ScoreTilesProps): JSX.Element {
  if (latest === null) {
    return (
      <div className="score-tiles" role="status" aria-label="scores not yet available">
        <Hero value={null} above={false} caption="waiting for the first frame" />
        <Tile label="Confidence" value={null} delta="waiting for the first frame" />
        <Tile label="Pause threshold" value={threshold} delta="from the deterministic policy" />
      </div>
    );
  }
  const dScore = previous ? latest.spaghetti_score - previous.spaghetti_score : 0;
  const dConf = previous ? latest.confidence - previous.confidence : 0;
  const fmt = (d: number) =>
    `${d >= 0 ? "+" : ""}${d.toFixed(2)} since frame ${previous ? previous.frame_index : latest.frame_index}`;
  return (
    <div className="score-tiles">
      <Hero
        value={latest.spaghetti_score}
        above={latest.spaghetti_score >= threshold}
        caption={previous ? fmt(dScore) : `frame ${latest.frame_index}`}
      />
      <Tile
        label="Confidence"
        value={latest.confidence}
        delta={previous ? fmt(dConf) : `frame ${latest.frame_index}`}
      />
      <Tile label="Pause threshold" value={threshold} delta="from the deterministic policy" />
    </div>
  );
}

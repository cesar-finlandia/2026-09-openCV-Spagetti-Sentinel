import type { JSX } from "react";

export type DegradedBannerProps = { reasons: string[] };

export function DegradedBanner({ reasons }: DegradedBannerProps): JSX.Element | null {
  if (reasons.length === 0) return null;
  if (reasons.length > 3) {
    const [first, second, ...rest] = reasons;
    return (
      <div className="degraded-banner" role="status" aria-live="polite">
        Running degraded: {first}, {second}{" "}
        <details>
          <summary>and {rest.length + 1} more</summary>
          {reasons.slice(2).join(", ")}
        </details>
      </div>
    );
  }
  return (
    <div className="degraded-banner" role="status" aria-live="polite">
      Running degraded: {reasons.join(", ")}
    </div>
  );
}

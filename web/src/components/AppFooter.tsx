import type { JSX } from "react";
import type { Health } from "../api";
import type { RunHeader } from "../selectors";

export type AppFooterProps = { header: RunHeader; health: Health | null };

export function AppFooter({ header, health }: AppFooterProps): JSX.Element {
  return (
    <footer className="app-footer" role="contentinfo" aria-label="About this system">
      {header?.synthetic ? (
        <p className="small">Demo footage is synthetic — generated for evaluation, watermarked.</p>
      ) : null}
      <p className="strong">This system recommends; it never controls the printer.</p>
      {health ? <p className="mono small">build {health.build_marker}</p> : null}
    </footer>
  );
}

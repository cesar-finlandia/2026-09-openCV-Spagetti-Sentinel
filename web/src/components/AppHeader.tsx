import { useEffect, useState, type JSX } from "react";
import type { Health } from "../api";
import type { RunHeader } from "../selectors";
import type { ThemeId } from "../theme";
import { BackendBadge } from "./BackendBadge";
import { ConnectionPill } from "./ConnectionPill";
import { NozzleGlyph } from "./Glyphs";
import { ThemeToggle } from "./ThemeToggle";

export type AppHeaderProps = {
  header: RunHeader;
  health: Health | null;
  status: "connecting" | "open" | "closed" | "error";
  onReconnect: () => void;
  theme: ThemeId;
  onThemeChange: (t: ThemeId) => void;
};

export function AppHeader({ header, health, status, onReconnect, theme, onThemeChange }: AppHeaderProps): JSX.Element {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 0);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <header className={scrolled ? "app-header scrolled" : "app-header"}>
      <div className="wordmark">
        <span aria-hidden="true">
          <NozzleGlyph size={20} />
        </span>
        <span className="display wordmark-text">Spaghetti Sentinel</span>
      </div>
      <div className="header-tools">
        <BackendBadge header={header} health={health} />
        <ConnectionPill status={status} onReconnect={onReconnect} />
        <ThemeToggle theme={theme} onChange={onThemeChange} />
      </div>
    </header>
  );
}

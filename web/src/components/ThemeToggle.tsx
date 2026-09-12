import type { JSX } from "react";
import type { ThemeId } from "../theme";
import { MoonGlyph, SunGlyph } from "./Glyphs";

export type ThemeToggleProps = { theme: ThemeId; onChange: (t: ThemeId) => void };

export function ThemeToggle({ theme, onChange }: ThemeToggleProps): JSX.Element {
  const dark = theme === "dark";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="theme-toggle"
      data-theme-state={theme}
      onClick={() => onChange(dark ? "light" : "dark")}
    >
      <span className="knob" aria-hidden="true">
        {dark ? <MoonGlyph /> : <SunGlyph />}
      </span>
    </button>
  );
}

import type { JSX } from "react";
// Inline SVG authored for this entry; no icon package, nothing traced.
// Each glyph is decorative: aria-hidden, not focusable. The accessible name
// always comes from the control that contains it.
export function NozzleGlyph({ size = 20 }: { size?: number }): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <path d="M4 2h12v4l-4 3v6l-4 3-4-3V9L4 6V2z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M10 9v6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function SunGlyph({ size = 16 }: { size?: number }): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <circle cx="8" cy="8" r="3" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6L13 13M13 3l-1.4 1.4M4.4 11.6L3 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function MoonGlyph({ size = 16 }: { size?: number }): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path d="M13 10.5A5.5 5.5 0 0 1 5.5 3 5.5 5.5 0 1 0 13 10.5z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

export function DownloadGlyph({ size = 14 }: { size?: number }): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" aria-hidden="true" focusable="false">
      <path d="M7 1v8M3.5 6L7 9.5 10.5 6M2 11.5h10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ChevronGlyph({ size = 14, open = false }: { size?: number; open?: boolean }): JSX.Element {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" aria-hidden="true" focusable="false">
      <path
        d={open ? "M3 8.5L7 4.5L11 8.5" : "M3 5.5L7 9.5L11 5.5"}
        fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
      />
    </svg>
  );
}

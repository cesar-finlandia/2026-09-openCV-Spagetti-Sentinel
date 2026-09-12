export type ThemeId = "light" | "dark";

export const THEME_STORAGE_KEY = "ss-theme";

function prefers(): ThemeId {
  try {
    if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
  } catch {
    /* missing matchMedia — fall through to light */
  }
  return "light";
}

/** Reads localStorage["ss-theme"], else prefers-color-scheme. Never throws. */
export function initialTheme(): ThemeId {
  try {
    const v = localStorage.getItem(THEME_STORAGE_KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    return prefers();
  }
  return prefers();
}

/** Sets document.documentElement.dataset.theme and persists. Never throws. */
export function applyTheme(id: ThemeId): void {
  try {
    document.documentElement.dataset.theme = id;
  } catch {
    /* no document — ignore */
  }
  try {
    localStorage.setItem(THEME_STORAGE_KEY, id);
  } catch {
    /* private window — ignore */
  }
}

/** Persist-free read of the stored preference; null when the user has not chosen. */
export function storedTheme(): ThemeId | null {
  try {
    const v = localStorage.getItem(THEME_STORAGE_KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    return null;
  }
  return null;
}

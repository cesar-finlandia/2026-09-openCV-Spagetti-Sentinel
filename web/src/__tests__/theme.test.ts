// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { THEME_STORAGE_KEY, applyTheme, initialTheme, storedTheme } from "../theme";

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
  try {
    localStorage.clear();
  } catch {
    /* ignore */
  }
});

describe("theme", () => {
  it("initialTheme returns the stored value when localStorage has dark", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    expect(initialTheme()).toBe("dark");
  });

  it("initialTheme falls back to matchMedia when nothing is stored (DP-UI-V2 §4.4: dark default)", () => {
    // the query is now (prefers-color-scheme: light) — a match means the user
    // explicitly prefers light; anything else gets the camera's theme, dark.
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    expect(initialTheme()).toBe("light");
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    expect(initialTheme()).toBe("dark");
  });

  it("initialTheme returns dark when localStorage.getItem throws", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {},
    });
    expect(initialTheme()).toBe("dark");
  });

  it("applyTheme sets dataset.theme and persists", () => {
    applyTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("applyTheme does not throw when localStorage.setItem throws", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem: () => {
        throw new Error("denied");
      },
    });
    expect(() => applyTheme("dark")).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("storedTheme is null when the user has not chosen", () => {
    expect(storedTheme()).toBeNull();
    localStorage.setItem(THEME_STORAGE_KEY, "light");
    expect(storedTheme()).toBe("light");
  });
});

// Dark (default) or light. Stored per device; applied to <html data-theme> before the first render.
export type Theme = "dark" | "light";

const KEY = "snazzlebop:theme";
const BAR = { dark: "#140b1b", light: "#fff1dc" };
const listeners = new Set<() => void>();

function stored(): Theme {
  try {
    return localStorage.getItem(KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

let current: Theme = stored();

function apply() {
  document.documentElement.dataset.theme = current;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", BAR[current]);
}
apply();

export const theme = {
  subscribe(fn: () => void) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
  get: () => current,
  set(next: Theme) {
    current = next;
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* fine: just not remembered */
    }
    apply();
    listeners.forEach((fn) => fn());
  },
};

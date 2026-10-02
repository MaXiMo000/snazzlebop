import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

const motionQuery = "(prefers-reduced-motion: reduce)";

export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia(motionQuery);
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => window.matchMedia(motionQuery).matches,
  );
}

/** Animates a number towards `value` (ease-out). Jumps straight there with reduced motion. */
export function useCountUp(value: number, ms = 900): number {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    if (reduced || from.current === value) {
      from.current = value;
      setShown(value);
      return;
    }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      const eased = 1 - (1 - t) ** 3;
      setShown(Math.round(a + (value - a) * eased));
      if (t < 1) raf = requestAnimationFrame(step);
      else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      from.current = value;
    };
  }, [value, ms, reduced]);
  return shown;
}

/** Runs `fn(prev, next)` whenever `value` changes after the first render. */
export function useOnChange<T>(value: T, fn: (prev: T, next: T) => void): void {
  const prev = useRef(value);
  const cb = useRef(fn);
  cb.current = fn;
  useEffect(() => {
    if (!Object.is(prev.current, value)) cb.current(prev.current, value);
    prev.current = value;
  }, [value]);
}

interface Shot {
  id: number;
  text: string;
  tone: "good" | "bad";
}

/**
 * Show-stoppers: a slammed-on sign ("DING DING!") and optional confetti. Both are decorative
 * (aria-hidden): the real result is always in the page content and announced there.
 */
export function useShow() {
  const [shot, setShot] = useState<Shot | null>(null);
  const [confetti, setConfetti] = useState(0);
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);

  const stinger = useCallback((text: string, tone: Shot["tone"] = "good") => {
    const id = Date.now();
    setShot({ id, text, tone });
    timers.current.push(window.setTimeout(() => setShot((s) => (s?.id === id ? null : s)), 1600));
  }, []);
  const celebrate = useCallback(() => {
    const id = Date.now();
    setConfetti(id);
    timers.current.push(window.setTimeout(() => setConfetti((c) => (c === id ? 0 : c)), 3600));
  }, []);

  const node = (
    <>
      {shot && (
        <div key={`s${shot.id}`} className={`stinger ${shot.tone === "bad" ? "bad" : ""}`} aria-hidden="true">
          {shot.text}
        </div>
      )}
      {confetti !== 0 && (
        <div key={`c${confetti}`} className="confetti" aria-hidden="true">
          {Array.from({ length: 36 }, (_, i) => (
            <i key={i} />
          ))}
        </div>
      )}
    </>
  );
  return { node, stinger, celebrate };
}

// Game-show sound effects, synthesised with WebAudio: no audio files, nothing fetched.
// Off by default; the toggle lives in the top bar and is remembered per device.

const KEY = "snazzlebop:sound";
let enabled = false;
let ctx: AudioContext | null = null;
const listeners = new Set<() => void>();

try {
  enabled = localStorage.getItem(KEY) === "on";
} catch {
  /* storage blocked: stay off */
}

export const sound = {
  subscribe(fn: () => void) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
  get: () => enabled,
  set(on: boolean) {
    enabled = on;
    try {
      localStorage.setItem(KEY, on ? "on" : "off");
    } catch {
      /* fine: just not remembered */
    }
    if (on) {
      // Created inside the click that turned sound on, so browsers allow it to play.
      ctx ??= new AudioContext();
      void ctx.resume();
      sfx.ding();
    }
    listeners.forEach((fn) => fn());
  },
};

function audio(): AudioContext | null {
  if (!enabled) return null;
  if (!ctx) {
    // Sound was on from a previous visit: we can only start after a user gesture.
    try {
      ctx = new AudioContext();
    } catch {
      return null;
    }
  }
  if (ctx.state === "suspended") void ctx.resume();
  return ctx.state === "running" ? ctx : null;
}

function note(freq: number, at: number, dur: number, type: OscillatorType = "sine", vol = 0.18, slideTo?: number) {
  const a = audio();
  if (!a) return;
  const t = a.currentTime + at;
  const osc = a.createOscillator();
  const gain = a.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t);
  if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, t + dur);
  gain.gain.setValueAtTime(0.0001, t);
  gain.gain.exponentialRampToValueAtTime(vol, t + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  osc.connect(gain).connect(a.destination);
  osc.start(t);
  osc.stop(t + dur + 0.02);
}

export const sfx = {
  /** correct answer / reveal bell */
  ding() {
    note(1318.5, 0, 0.5, "sine", 0.2);
    note(1760, 0.09, 0.7, "sine", 0.16);
  },
  /** wrong / contradiction buzzer */
  buzz() {
    note(110, 0, 0.45, "sawtooth", 0.12);
    note(116, 0, 0.45, "square", 0.06);
  },
  /** countdown tick (last 5 seconds) */
  tick() {
    note(1046.5, 0, 0.06, "square", 0.07);
  },
  /** little button pop */
  pop() {
    note(660, 0, 0.09, "triangle", 0.14, 990);
  },
  /** reel clicking while the chaos spin turns */
  spin() {
    for (let i = 0; i < 14; i++) note(700 + (i % 2) * 120, i * (0.05 + i * 0.008), 0.035, "square", 0.05);
  },
  /** a token hopping one square */
  hop() {
    note(520, 0, 0.05, "triangle", 0.08, 780);
  },
  /** dice rattling in the cup, then landing */
  rattle() {
    for (let i = 0; i < 8; i++) note(380 + ((i * 97) % 260), i * 0.045, 0.03, "square", 0.05);
    note(220, 0.4, 0.08, "triangle", 0.14);
  },
  /** a walk-on jingle: the same few notes every time for the same seed (so each person has their own) */
  jingle(seed: number) {
    const scale = [523.3, 587.3, 659.3, 784, 880, 1046.5];
    let h = seed >>> 0;
    for (let i = 0; i < 5; i++) {
      h = (h * 1103515245 + 12345) >>> 0;
      note(scale[(h >>> 16) % scale.length]!, i * 0.13, 0.16, "triangle", 0.16);
    }
    note(1046.5, 0.68, 0.7, "triangle", 0.18);
    note(1318.5, 0.68, 0.7, "sine", 0.1);
  },
  /** winner fanfare */
  fanfare() {
    [523.3, 659.3, 784, 1046.5].forEach((f, i) => note(f, i * 0.11, i === 3 ? 0.7 : 0.16, "triangle", 0.17));
  },
};

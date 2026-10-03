// WCAG contrast check for every text/background pair used in src/styles.css.
//   node scripts/contrast.mjs     -> exits 1 if any pair is below 4.5:1
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const root = css.slice(css.indexOf(":root {"), css.indexOf("}", css.indexOf(":root {")));
const v = Object.fromEntries([...root.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]));
const c = (x) => (x.startsWith("#") ? x : v[x] ?? (() => { throw new Error(`unknown colour ${x}`); })());

const lum = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((u) => (u <= 0.03928 ? u / 12.92 : ((u + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => {
  const [x, y] = [lum(c(a)), lum(c(b))].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

// [text, background, where]
const pairs = [
  ["plum", "cream", "body text"],
  ["plum", "paper", "cards"],
  ["plum", "cream-2", "soft cards (default)"],
  ["plum", "#ffffff", "inputs, tables"],
  ["plum-soft", "cream", "muted text on page"],
  ["plum-soft", "paper", "muted text in cards"],
  ["plum-soft", "cream-2", "muted text in soft cards"],
  ["plum-soft", "#ffffff", "struck-out guesses"],
  ["plum-soft", "cherry-light", "muted in frenemy soft"],
  ["plum-soft", "#c9eef2", "muted in alibi soft"],
  ["plum-soft", "#fff0b8", "muted in price soft"],
  ["#7d6683", "#ffffff", "input placeholder"],
  ["plum", "tangerine", "primary button, logo badge"],
  ["plum", "mustard", "gold button, price tag, price segment"],
  ["plum", "bulb", "signs, chips, arrows, clues"],
  ["plum", "teal-light", "your row / chip"],
  ["plum", "cherry-light", "lie cells, frenemy soft"],
  ["plum", "#c9eef2", "alibi soft"],
  ["plum", "#fff0b8", "price soft"],
  ["#6b4f73", "#e9dccb", "disabled buttons (exempt, checked anyway)"],
  ["cream", "teal", "go button, alibi segment, teal chip"],
  ["#ffffff", "cherry", "danger button, frenemy segment, flags, urgent clock"],
  ["cream", "plum", "stage text"],
  ["#e7d3c4", "plum", "muted text on stage"],
  ["bulb", "plum", "clock, table head, plum chip, tagline, pressed button"],
  ["bulb", "#3b2546", "split-flap (top half)"],
  ["bulb", "#20132a", "split-flap (bottom half)"],
  ["teal", "#ffffff", "reel x1/2 (large)"],
  ["cherry", "#ffffff", "reel x2 (large)"],
  ["cherry", "cream", "logo bang"],
  ["#ffffff", "#5b2f9e", "Telepathy segment / accent buttons"],
  ["plum", "#e9defa", "Telepathy soft cards"],
  ["plum-soft", "#e9defa", "muted in Telepathy soft"],
  ["plum", "#ffe1cf", "Mural soft cards"],
  ["plum-soft", "#ffe1cf", "muted in Mural soft"],
  ["plum-soft", "paper", "mural tile tags"],
  ["plum", "tangerine", "selected mural tile (Mural accent)"],
  ["#ffffff", "#11643f", "Blackjack segment / felt"],
  ["bulb", "#11643f", "sign text on felt"],
  ["cream", "#147043", "text on the felt's lightest point"],
  ["bulb", "#147043", "sign on the felt's lightest point"],
  ["plum", "#d6efe0", "Blackjack soft cards"],
  ["plum-soft", "#d6efe0", "muted in Blackjack soft"],
  ["#ffffff", "#1f5fae", "Crossword segment"],
  ["plum", "#dbe8fb", "Crossword soft cards"],
  ["plum-soft", "#dbe8fb", "muted in Crossword soft"],
  ["cherry", "#ffffff", "red playing cards"],
  ["#ffffff", "#a3195b", "Jackpot segment"],
  ["#ffffff", "#8c2f39", "Liar's Dice segment, hot dice"],
  ["#ffffff", "#0b6e4f", "Split or Steal segment"],
  ["plum", "#d3f0e4", "Split or Steal soft cards"],
  ["plum-soft", "#d3f0e4", "muted in Split or Steal soft"],
  ["plum", "#f8dde0", "Liar's Dice soft cards"],
  ["plum-soft", "#f8dde0", "muted in Liar's Dice soft"],
  ["plum", "#fbe0ec", "Jackpot soft cards"],
  ["plum-soft", "#fbe0ec", "muted in Jackpot soft"],
  ["bulb", "plum", "reaction name tags"],
  ["plum", "teal-light", "done show segments"],
  ["plum", "cream", "highlight items"],
];

let bad = 0;
for (const [fg, bg, where] of pairs) {
  const r = ratio(fg, bg);
  const ok = r >= 4.5;
  if (!ok) bad++;
  console.log(`${ok ? "ok  " : "FAIL"} ${r.toFixed(2).padStart(5)}:1  ${fg} on ${bg}  (${where})`);
}
process.exit(bad ? 1 : 0);

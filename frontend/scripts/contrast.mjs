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
  ["#ffffff", "#b34700", "Chicken Run segment"],
  ["#ffffff", "#3d4fa3", "Wager Wits segment"],
  ["#ffffff", "#5c4a1f", "Code Crackers segment"],
  ["#ffffff", "#7a1f3d", "Roulette segment"],
  ["#ffffff", "#0f5a73", "Lowest Lonely segment"],
  ["#ffffff", "#2c2f5e", "Codewords segment (setup)"],
  ["#ffffff", "#c8203a", "Codewords red card / pill"],
  ["#ffffff", "#1f5fae", "Codewords blue card / pill"],
  ["plum", "#b59c74", "Codewords bystander (revealed)"],
  ["#ffffff", "#141014", "Codewords assassin"],
  ["plum", "#f6ead6", "Codewords face-down card"],
  ["plum", "#f6c7cf", "Codewords key: red"],
  ["plum", "#c9dbf4", "Codewords key: blue"],
  ["plum", "#ece2cf", "Codewords key: bystander"],
  ["#ffffff", "#3a3438", "Codewords key: assassin"],
  ["#ff9aa9", "#2e1d3d", "Codewords clue problem (dark soft card)"],
  ["plum", "#d4ecf3", "Lowest Lonely soft cards"],
  ["plum-soft", "#d4ecf3", "muted in Lowest Lonely soft"],
  ["#ffffff", "#8a3b12", "Mystery Box segment"],
  ["plum", "#f6e0d2", "Mystery Box soft cards"],
  ["plum-soft", "#f6e0d2", "muted in Mystery Box soft"],
  ["#ffffff", "#14532d", "Stock Exchange segment"],
  ["plum", "#f6dbe4", "Roulette soft cards"],
  ["plum-soft", "#f6dbe4", "muted in Roulette soft"],
  ["#ffffff", "#b3122e", "red pockets"],
  ["#ffffff", "#1d1d1d", "black pockets"],
  ["#ffffff", "#0d6b3a", "green pocket"],
  ["plum", "#f1e8d0", "Code Crackers soft cards"],
  ["plum-soft", "#f1e8d0", "muted in Code Crackers soft"],
  ["plum", "#e0e5fa", "Wager Wits soft cards, picked slots"],
  ["plum-soft", "#e0e5fa", "muted in Wager Wits soft"],
  ["plum", "#ffe3cc", "Chicken Run soft cards"],
  ["plum-soft", "#ffe3cc", "muted in Chicken Run soft"],
  ["plum", "#d3f0e4", "Split or Steal soft cards"],
  ["plum-soft", "#d3f0e4", "muted in Split or Steal soft"],
  ["plum", "#f8dde0", "Liar's Dice soft cards"],
  ["plum-soft", "#f8dde0", "muted in Liar's Dice soft"],
  ["plum", "#fbe0ec", "Jackpot soft cards"],
  ["plum-soft", "#fbe0ec", "muted in Jackpot soft"],
  ["bulb", "plum", "reaction name tags"],
  ["plum", "teal-light", "done show segments"],
  ["plum", "cream", "highlight items"],
  ["#ffffff", "#9c2a5c", "Truth or Dare segment"],
  ["plum", "#f9dfea", "Truth or Dare soft cards"],
  ["plum-soft", "#f9dfea", "muted in Truth or Dare soft"],
  ["bulb", "#3b2546", "Truth or Dare seats"],
  ["cream", "teal", "Truth door"],
  ["#ffffff", "cherry", "Dare door"],
  ["#ffffff", "#2e7d32", "Word Race segment, green tiles"],
  ["#ffffff", "#9a6a00", "Word Race yellow tiles"],
  ["#ffffff", "#57505e", "Word Race grey tiles"],
  ["plum", "#dcefd9", "Word Race soft cards"],
  ["plum-soft", "#dcefd9", "muted in Word Race soft"],
  ["#2e7d32", "paper", "Word Race answers list (light)"],
  ["#7fd17a", "#221530", "Word Race answers list (dark)"],
  ["cream", "#4a3760", "Word Race untried keys (dark)"],
  ["#ffffff", "#127a3e", "Last Card green cards"],
  ["#ffffff", "#1f5fae", "Last Card blue cards"],
  ["#ffffff", "#c8203a", "Last Card red cards"],
  ["plum", "#f2b705", "Last Card yellow cards"],
  ["#9a6a00", "#ffffff", "Last Card yellow symbol in the oval"],
  ["#127a3e", "#ffffff", "Last Card green symbol in the oval"],
  ["#ffffff", "#241a2b", "Last Card wild cards and backs"],
  ["bulb", "#c8203a", "Last Card back mark"],
  ["plum", "#ffd3d8", "Last Card soft cards"],
  ["plum-soft", "#ffd3d8", "muted in Last Card soft"],
  ["#ffffff", "#1f4e45", "Chess segment"],
  ["plum", "#d3e9e3", "Chess soft cards"],
  ["plum-soft", "#d3e9e3", "muted in Chess soft"],
  ["#5b3a1e", "#f1e0bf", "Chess coordinates on light squares"],
  ["plum", "#b8875a", "Chess coordinates on dark squares"],
  ["#ffffff", "#c2185b", "Draw & Guess segment"],
  ["plum", "#fbd5e5", "Draw & Guess soft cards"],
  ["plum-soft", "#fbd5e5", "muted in Draw & Guess soft"],
  ["#ffffff", "#1d6fa5", "Draw Telephone segment, liked pages"],
  ["plum", "#d4e8f5", "Draw Telephone soft cards"],
  ["plum-soft", "#d4e8f5", "muted in Draw Telephone soft"],
  ["#ffffff", "#8a5a14", "Property Tycoon segment"],
  ["#ffffff", "#4a1d6b", "Mafia Night segment"],
  ["plum", "#e6d8f3", "Mafia Night soft cards"],
  ["plum-soft", "#e6d8f3", "muted in Mafia Night soft"],
  ["plum", "#f3e3c3", "Property Tycoon soft cards, the player on turn"],
  ["#5b4466", "#f3e3c3", "muted text on the player on turn"],
  ["plum", "#fffaf1", "Property Tycoon board squares"],
  ["#8a5a14", "#e6f2df", "Property Tycoon board logo"],
  ["plum", "tangerine", "Team Tangerine chips and labels"],
  ["#ffffff", "teal", "Team Teal chips and labels"],
  ["#ff8f5c", "#221530", "Team Tangerine name (dark cards)"],
  ["#5fd0d3", "#221530", "Team Teal name (dark cards)"],
  ["#b34700", "#fffaf1", "Team Tangerine name (light cards)"],
  ["#0b7476", "#fffaf1", "Team Teal name (light cards)"],
  ["#8ee6a0", "#2b1239", "Blackjack: your win on the stage (dark)"],
  ["#8ee6a0", "#2b1b33", "Blackjack: your win on the stage (light)"],
  ["#ffb3bd", "#2b1239", "Blackjack: your loss on the stage (dark)"],
  ["#ffb3bd", "#2b1b33", "Blackjack: your loss on the stage (light)"],
  ["#ffffff", "#c8203a", "Ludo red: header, token numbers"],
  ["#ffffff", "#127a3e", "Ludo green: header, token numbers"],
  ["#ffffff", "#1f5fae", "Ludo blue: header, token numbers"],
  ["plum", "#f2b705", "Ludo yellow: header, token numbers"],
  ...["#ffd3d8", "#c8ecd5", "#ffeaa0", "#cfe0f7"].flatMap((bg) => [
    ["plum", bg, "Ludo soft cards and the team on turn"],
    ["plum-soft", bg, "muted in Ludo soft"],
  ]),
];

// Dark theme (the default): role tokens from :root, plus each segment's soft tint, which is
// color-mix(in srgb, accent 26%, #1b1024) in the stylesheet.
const mix = (a, b, t) => {
  const [x, y] = [c(a), c(b)];
  const ch = (h, i) => parseInt(h.slice(i, i + 2), 16);
  return "#" + [1, 3, 5].map((i) => Math.round(ch(x, i) * t + ch(y, i) * (1 - t)).toString(16).padStart(2, "0")).join("");
};
const accents = ["cherry", "teal", "mustard", "tangerine", "#0b6e4f", "#0f5a73", "#11643f", "#14532d", "#1f5fae", "#3d4fa3", "#5b2f9e", "#5c4a1f", "#7a1f3d", "#8a3b12", "#8c2f39", "#a3195b", "#b34700", "#127a3e", "#f2b705", "#1f4e45", "#c2185b", "#1d6fa5", "#8a5a14", "#4a1d6b"];
pairs.push(
  ["ink", "bg", "dark: body text"],
  ["ink", "surface", "dark: cards"],
  ["ink", "surface-2", "dark: soft cards (default)"],
  ["ink", "field", "dark: inputs, tables"],
  ["ink", "stage", "dark: stage text"],
  ["bulb", "stage", "dark: lit text on the stage"],
  ["muted", "bg", "dark: muted on page"],
  ["muted", "surface", "dark: muted in cards"],
  ["muted", "surface-2", "dark: muted in soft cards"],
  ["muted", "field", "dark: muted in tables"],
  ["placeholder", "field", "dark: input placeholder"],
  ["disabled-fg", "disabled-bg", "dark: disabled buttons"],
  ["ink", "#134a52", "dark: your row / done segments (teal-light)"],
  ["ink", "#4f1b29", "dark: lie cells, frenemy soft (cherry-light)"],
  ...accents.flatMap((a) => [
    ["ink", mix(a, "#1b1024", 0.26), `dark: soft card tint of ${a}`],
    ["muted", mix(a, "#1b1024", 0.26), `dark: muted in soft tint of ${a}`],
  ]),
);

let bad = 0;
for (const [fg, bg, where] of pairs) {
  const r = ratio(fg, bg);
  const ok = r >= 4.5;
  if (!ok) bad++;
  console.log(`${ok ? "ok  " : "FAIL"} ${r.toFixed(2).padStart(5)}:1  ${fg} on ${bg}  (${where})`);
}
process.exit(bad ? 1 : 0);

// Dev tool (not production). With the API on :8000 (JUMPSCARE=false) and web on :5173:
//   cd frontend && node ../docs/handoff/tools/capture.cjs <out dir> [truthdare wordrace lastcard ludo]
//   (FIVE=1 adds a fifth player on a 320px phone: Ludo then plays in teams)
// Plays Truth or Dare, Word Race and Last Card with four real browser players (laptop, phone, tablet,
// small phone) plus a TV screen, and screenshots every device at every phase.
const fs = require("fs");
const path = require("path");
const REPO = path.resolve(__dirname, "../../..");
const FRONT = path.join(REPO, "frontend");
const { chromium } = require(FRONT + "/node_modules/@playwright/test");

const OUT = process.argv[2];
const ONLY = process.argv.slice(3);
const BASE = "http://localhost:5173";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
fs.mkdirSync(OUT, { recursive: true });

const DEVICES = [
  { key: "laptop", label: "Laptop (1366px, light)", name: "Ana", viewport: { width: 1366, height: 768 }, theme: "light", dsf: 1 },
  { key: "phone", label: "Phone (390px, dark)", name: "Bartholomew X", viewport: { width: 390, height: 844 }, theme: "dark", mobile: true, dsf: 2 },
  { key: "tablet", label: "Tablet (820px, dark)", name: "Zara", viewport: { width: 820, height: 1180 }, theme: "dark", mobile: true, dsf: 1 },
  { key: "small", label: "Small phone (360px, light)", name: "Leo", viewport: { width: 360, height: 780 }, theme: "light", mobile: true, dsf: 2 },
];
// A fifth player on the smallest phone, only when asked for (Ludo: five players = teams sharing a colour).
const TINY = { key: "tiny", label: "Tiny phone (320px, dark)", name: "Alexandria Wood", viewport: { width: 320, height: 640 }, theme: "dark", mobile: true, dsf: 2 };
if (process.env.FIVE) DEVICES.push(TINY);
const TV = { key: "tv", label: "TV screen (1920px)", viewport: { width: 1920, height: 1080 }, theme: "dark", dsf: 1 };

const MANIFEST = path.join(OUT, "manifest.json");
const shots = fs.existsSync(MANIFEST) && ONLY.length
  ? JSON.parse(fs.readFileSync(MANIFEST, "utf8")).filter((s) => !ONLY.includes(s.game))
  : [];
let seq = ONLY.length ? 500 : 0;

async function shot(game, step, title, who, opts = {}) {
  await sleep(opts.wait ?? 900);
  for (const p of who) {
    const file = `${game}-${String(++seq).padStart(3, "0")}-${step}-${p.dev.key}.jpg`;
    try {
      await p.page.screenshot({ path: path.join(OUT, file), fullPage: p.dev.key !== "tv", type: "jpeg", quality: 72 });
      shots.push({ game, step, title, device: p.dev.key, label: p.dev.label, file });
    } catch (e) {
      console.log("shot failed", file, e.message.split("\n")[0]);
    }
  }
  fs.writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify(shots, null, 1));
}

const sign = (p) => p.page.locator(".show-head .sign").first().textContent({ timeout: 500 }).catch(() => "");
async function until(fn, label, ms = 60000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const v = await fn();
    if (v) return v;
    await sleep(200);
  }
  throw new Error("timeout: " + label);
}
const has = (p, sel) => p.page.locator(sel).first().isVisible().catch(() => false);
// force: pulsing buttons (LAST CARD!, Catch) never hold still, which Playwright otherwise waits out.
const click = (p, sel) => p.page.locator(sel).first().click({ timeout: 3000, force: true }).catch(() => undefined);
const btn = (p, re) => p.page.getByRole("button", { name: re }).first();

async function readyAll(players) {
  for (const p of players) await btn(p, /I’m ready/).click({ timeout: 4000 }).catch(() => undefined);
}

async function startGame(host, id) {
  const card = host.page.locator(`article.game-card.seg-${id}`);
  await card.scrollIntoViewIfNeeded();
  await card.getByRole("button", { name: /Start!/ }).click();
}

async function toLobby(host) {
  await btn(host, /Play another game/).click({ timeout: 10000 }).catch(() => undefined);
  await sleep(1200);
}

// ---------------------------------------------------------------------------------------------------
async function truthOrDare(players, tv, host) {
  const all = [...players, tv];
  await startGame(host, "truthdare");
  await until(async () => (await sign(host)).includes("how to play"), "tod intro");
  await shot("truthdare", "intro", "The rules before it starts", all);
  await readyAll(players);
  const seen = new Set();
  let turn = 0;
  for (let i = 0; i < 400; i++) {
    const s = await sign(host);
    if (s.includes("Final")) break;
    if (s.includes("Spin the bottle")) {
      if (!seen.has("spin")) {
        seen.add("spin");
        await shot("truthdare", "spin", "The bottle spins", all, { wait: 1500 });
      }
      await btn(host, /Skip wait/).click({ timeout: 3000 }).catch(() => undefined);
      await sleep(600);
      continue;
    }
    if (s.includes("Truth or dare?")) {
      const target = await until(async () => {
        for (const p of players) if (await has(p, ".tod-door")) return p;
        return null;
      }, "target", 8000).catch(() => null);
      if (!target) continue;
      if (!seen.has("choose")) {
        seen.add("choose");
        await shot("truthdare", "choose", `The bottle picked ${target.dev.name}: Truth or Dare doors (others wait)`, all);
      }
      turn++;
      await click(target, turn % 2 ? ".tod-door.dare" : ".tod-door.truth");
      await sleep(900);
      continue;
    }
    if (s.includes("Do the dare") || s.includes("Tell the truth")) {
      const target = await until(async () => {
        for (const p of players) if (await btn(p, /Judge me/).isVisible().catch(() => false)) return p;
        return null;
      }, "performer", 8000).catch(() => null);
      if (!target) continue;
      const kind = s.includes("dare") ? "dare" : "truth";
      if (!seen.has("perform-" + kind)) {
        seen.add("perform-" + kind);
        await shot("truthdare", "perform-" + kind, `The ${kind} card flips in for everyone`, all, { wait: 1300 });
      }
      if (turn === 3 && !seen.has("chicken")) {
        seen.add("chicken");
        target.page.once("dialog", (d) => d.accept());
        await btn(target, /Chicken out/).click({ timeout: 3000 }).catch(() => undefined);
        await sleep(1500);
        await shot("truthdare", "chicken", "Someone chickened out", all, { wait: 600 });
        await btn(host, /Skip wait/).click({ timeout: 3000 }).catch(() => undefined);
        await sleep(800);
        continue;
      }
      await btn(target, /Judge me/).click({ timeout: 3000 }).catch(() => undefined);
      await sleep(800);
      continue;
    }
    if (s.includes("The room decides")) {
      const voters = [];
      for (const p of players) if (await has(p, ".tod-votes")) voters.push(p);
      if (voters.length && !seen.has("vote")) {
        seen.add("vote");
        await voters[0].page.locator(".tod-votes button").first().click();
        await sleep(500);
        await shot("truthdare", "vote", "The room votes: thumbs up or down (one vote already in)", all, { wait: 600 });
      }
      for (const [j, p] of voters.entries()) {
        await p.page.locator(".tod-votes button").nth(j === 1 && turn % 3 === 0 ? 1 : 0).click({ timeout: 2000 }).catch(() => undefined);
      }
      await sleep(900);
      continue;
    }
    if (s.includes("The verdict")) {
      if (!seen.has("verdict")) {
        seen.add("verdict");
        await shot("truthdare", "verdict", "The verdict and the points", all, { wait: 1400 });
      }
      await btn(host, /Skip wait/).click({ timeout: 3000 }).catch(() => undefined);
      await sleep(700);
      continue;
    }
    await sleep(300);
  }
  await shot("truthdare", "final", "Final scores, every turn and the awards", all, { wait: 2500 });
  await toLobby(host);
}

// ---------------------------------------------------------------------------------------------------
function loadAnswers() {
  const src = fs.readFileSync(path.join(REPO, "backend/app/games/content.py"), "utf8");
  const m = /WORD_ANSWERS: list\[str\] = _words\(\s*"""([\s\S]*?)"""/.exec(src);
  return m[1].split(/\s+/).filter(Boolean);
}
function marks(guess, answer) {
  const out = Array(5).fill("x");
  const spare = {};
  for (let i = 0; i < 5; i++) {
    if (guess[i] === answer[i]) out[i] = "g";
    else spare[answer[i]] = (spare[answer[i]] || 0) + 1;
  }
  for (let i = 0; i < 5; i++) {
    if (out[i] !== "g" && spare[guess[i]]) {
      out[i] = "y";
      spare[guess[i]]--;
    }
  }
  return out.join("");
}
async function myRows(p) {
  return p.page.$$eval(".wr-grid .wr-row", (rows) =>
    rows
      .map((r) => [...r.querySelectorAll(".wr-tile")].map((t) => ({ ch: t.textContent.trim(), m: (t.className.match(/m-([gyx])/) || [])[1] || "" })))
      .filter((r) => r.every((t) => t.m))
      .map((r) => ({ word: r.map((t) => t.ch).join(""), marks: r.map((t) => t.m).join("") })),
  );
}

async function wordRace(players, tv, host) {
  const all = [...players, tv];
  const answers = loadAnswers();
  await startGame(host, "wordrace");
  await until(async () => (await sign(host)).includes("how to play"), "wr intro");
  await shot("wordrace", "intro", "The rules before it starts", all);
  await readyAll(players);
  for (let round = 1; round <= 3; round++) {
    await until(async () => (await sign(host)).includes(`Word ${round} of 3`) && (await has(host, "#wr-guess")), "wr play " + round);
    if (round === 1) {
      await shot("wordrace", "start", "A fresh word: empty grids, letter board, guess box", all, { wait: 800 });
      const ph = players[1];
      await ph.page.locator("#wr-guess").fill("ASDFG");
      await ph.page.locator("#wr-guess").press("Enter");
      await shot("wordrace", "not-a-word", "Not a real word: the row shakes and a toast says so (no try used)", [ph], { wait: 350 });
      await ph.page.locator("#wr-guess").fill("");
    }
    const pools = players.map(() => [...answers]);
    for (let g = 0; g < 6; g++) {
      for (const [i, p] of players.entries()) {
        if (!(await has(p, "#wr-guess"))) continue;
        const rows = await myRows(p);
        pools[i] = pools[i].filter((w) => rows.every((r) => marks(r.word, w) === r.marks));
        // The first guesses are spread out so the screens show a race, not four identical boards.
        const word = g === 0 ? ["CRANE", "PILOT", "MOUSE", "DUSTY"][i] : pools[i][Math.floor(Math.random() * pools[i].length)];
        if (!word) continue;
        await p.page.locator("#wr-guess").fill(word);
        await p.page.locator("#wr-guess").press("Enter");
        await sleep(350);
      }
      await sleep(1700);
      if (round === 1 && g === 1) await shot("wordrace", "mid", "Mid-race: your letters, everyone else's colours only", all, { wait: 400 });
      if ((await sign(host)).includes("word was")) break;
    }
    await until(async () => (await sign(host)).includes("word was"), "wr reveal " + round, 30000).catch(() => undefined);
    if (round === 1) await shot("wordrace", "reveal", "The reveal: the word, who solved it, everyone's guesses", all, { wait: 1800 });
    await btn(host, /Skip wait/).click({ timeout: 3000 }).catch(() => undefined);
  }
  await until(async () => (await sign(host)).includes("Final"), "wr final", 30000).catch(() => undefined);
  await shot("wordrace", "final", "Final standings and every word", all, { wait: 2500 });
  await toLobby(host);
}

// ---------------------------------------------------------------------------------------------------
async function lastCard(players, tv, host) {
  const all = [...players, tv];
  await startGame(host, "lastcard");
  await until(async () => (await sign(host)).includes("how to play"), "lc intro");
  await shot("lastcard", "intro", "The rules before it starts", all);
  await readyAll(players);
  await until(async () => (await has(host, ".lc-table")), "lc table");
  await shot("lastcard", "deal", "The deal: seats, piles, the colour to match, your hand", all, { wait: 1200 });
  const seen = new Set();
  const leo = players[3];
  for (let i = 0; i < 1500; i++) {
    const s = await sign(host);
    if (s.includes("went out") || s.includes("Final")) break;
    // Anyone with a Catch button: capture it once, then catch.
    for (const p of players) {
      if (await has(p, ".lc-catch")) {
        if (!seen.has("catch")) {
          seen.add("catch");
          await shot("lastcard", "catch", "Leo forgot to call LAST CARD: everyone gets a Catch button", all, { wait: 300 });
        }
        await click(p, ".lc-catch");
        await sleep(500);
      }
    }
    let actor = null;
    for (const p of players) if ((await sign(p)).includes("Your turn")) actor = p;
    if (!actor) {
      await sleep(150);
      continue;
    }
    const playable = actor.page.locator(".lc-hand-btn.playable");
    const n = await playable.count();
    const take = actor.page.getByRole("button", { name: /^Take \d/ }).last();
    if (await take.isVisible().catch(() => false)) {
      if (!seen.has("pending")) {
        seen.add("pending");
        await shot("lastcard", "pending", "A draw card lands: take it (or challenge a Wild Draw Four)", all, { wait: 400 });
      }
      const challenge = btn(actor, /Challenge!/);
      if ((await challenge.isVisible().catch(() => false)) && Math.random() < 0.5) await challenge.click({ force: true });
      else if (n) await playable.first().click({ force: true });
      else await take.click({ force: true });
      await sleep(500);
      continue;
    }
    const last = btn(actor, /^LAST CARD!$/);
    if ((await last.isVisible().catch(() => false)) && actor !== leo) {
      await last.click({ force: true, timeout: 3000 }).catch(() => undefined);
      await sleep(400);
      if (!seen.has("called")) {
        seen.add("called");
        await shot("lastcard", "called", `${actor.dev.name} calls LAST CARD!`, all, { wait: 300 });
      }
    }
    if (n) {
      let card = playable.first();
      for (let j = 0; j < n; j++) {
        const label = await playable.nth(j).getAttribute("aria-label");
        if (/Wild/.test(label || "") && !seen.has("picker")) card = playable.nth(j);
      }
      const label = (await card.getAttribute("aria-label")) || "";
      if (!seen.has("myturn") && !/Wild/.test(label)) {
        seen.add("myturn");
        await shot("lastcard", "turn", `${actor.dev.name}'s turn: playable cards lift with a gold ring`, [actor, tv], { wait: 300 });
      }
      await card.click({ force: true, timeout: 3000 }).catch(() => undefined);
      if (/Wild/.test(label)) {
        await sleep(400);
        if (!seen.has("picker")) {
          seen.add("picker");
          await shot("lastcard", "picker", "Playing a Wild: pick the new colour", [actor], { wait: 300 });
        }
        await actor.page.locator(".lc-color").nth(Math.floor(Math.random() * 4)).click({ force: true });
      }
    } else if (await btn(actor, /Keep it/).isVisible().catch(() => false)) {
      await btn(actor, /Keep it/).click({ force: true });
    } else {
      await click(actor, ".lc-pile");
    }
    await sleep(450);
  }
  await until(async () => (await sign(host)).includes("went out"), "lc over", 30000).catch(() => undefined);
  await shot("lastcard", "hand-over", "Someone goes out: every hand is revealed and scored", all, { wait: 2200 });
  await btn(host, /Skip wait/).click({ timeout: 3000 }).catch(() => undefined);
  await until(async () => (await sign(host)).includes("Final"), "lc final", 30000).catch(() => undefined);
  await shot("lastcard", "final", "Final scores and the awards", all, { wait: 2500 });
  await toLobby(host);
}

// ---------------------------------------------------------------------------------------------------
async function ludo(players, tv, host) {
  const all = [...players, tv];
  await startGame(host, "ludo");
  await until(async () => (await sign(host)).includes("how to play"), "ludo intro");
  await shot("ludo", "intro", "The rules before it starts", all);
  await readyAll(players);
  await until(async () => await has(host, ".ludo-board"), "ludo board");
  await shot("ludo", "start", "The board: every token in its yard, whose turn it is, the teams", all, { wait: 1200 });
  const seen = new Set();
  const stinger = async (re) => {
    for (const p of players) if (re.test((await p.page.locator(".stinger").first().textContent({ timeout: 200 }).catch(() => "")) || "")) return true;
    return false;
  };
  for (let i = 0; i < 12000; i++) {
    const s = await sign(host);
    if (s.includes("wins!")) break;
    if (!seen.has("capture") && (await stinger(/KNOCK/))) {
      seen.add("capture");
      await shot("ludo", "capture", "A capture: the rival goes back to its yard", all, { wait: 100 });
    }
    if (!seen.has("first") && (await stinger(/WINS/))) {
      seen.add("first");
      await shot("ludo", "first", "1st place is home: the medal shows and play goes on for 2nd and 3rd", all, { wait: 100 });
    }
    if (!seen.has("home") && (await stinger(/HOME/))) {
      seen.add("home");
      await shot("ludo", "home", "A token reaches home", all, { wait: 100 });
    }
    if (i === 160 && !seen.has("mid")) {
      seen.add("mid");
      await shot("ludo", "midgame", "Mid-game: tokens round the board, sharing squares, the log", all, { wait: 400 });
    }
    let actor = null;
    for (const p of players) if ((await sign(p)).includes("Your turn")) actor = p;
    if (!actor) {
      await sleep(150);
      continue;
    }
    const roll = btn(actor, /Roll!/);
    if (await roll.isVisible().catch(() => false)) {
      if (!seen.has("roll")) {
        seen.add("roll");
        await shot("ludo", "roll", `${actor.dev.name}'s turn: the Roll button`, [actor, tv], { wait: 300 });
      }
      await roll.click({ force: true, timeout: 3000 }).catch(() => undefined);
      await sleep(250);
      continue;
    }
    const moves = actor.page.locator(".ludo-moves .btn");
    if ((await moves.count()) > 0) {
      if (!seen.has("choose")) {
        seen.add("choose");
        await shot("ludo", "choose", `${actor.dev.name} picks a token: movable tokens glow, buttons say what each move does`, [actor, tv], { wait: 300 });
      }
      await moves.first().click({ force: true, timeout: 3000 }).catch(() => undefined);
      await sleep(250);
      continue;
    }
    await sleep(150);
  }
  await until(async () => (await sign(host)).includes("wins!"), "ludo final", 60000).catch(() => undefined);
  await shot("ludo", "final", "A colour gets every token home: final scores and the awards", all, { wait: 3000 });
  await toLobby(host);
}

// ---------------------------------------------------------------------------------------------------
(async () => {
  const browser = await chromium.launch();
  const open = async (dev) => {
    const ctx = await browser.newContext({
      viewport: dev.viewport,
      deviceScaleFactor: dev.dsf,
      isMobile: !!dev.mobile,
      hasTouch: !!dev.mobile,
      colorScheme: dev.theme,
    });
    await ctx.addInitScript((t) => localStorage.setItem("snazzlebop:theme", t), dev.theme);
    const page = await ctx.newPage();
    return { dev: { ...dev, name: dev.name }, page };
  };
  const players = [];
  for (const d of DEVICES) players.push(await open(d));
  const host = players[0];
  await host.page.goto(BASE);
  await host.page.locator("#host-name").fill(host.dev.name);
  await host.page.locator("#host-name").press("Enter");
  await host.page.waitForURL(/\/r\/[A-Z]+/);
  const code = /\/r\/([A-Z]+)/.exec(host.page.url())[1];
  console.log("room", code);
  for (const p of players.slice(1)) {
    await p.page.goto(`${BASE}/r/${code}`);
    await p.page.locator("#join-name").fill(p.dev.name);
    await p.page.getByRole("button", { name: /Join as a contestant/ }).click();
    await p.page.waitForSelector(".contestants");
  }
  const tv = await open(TV);
  await tv.page.goto(`${BASE}/r/${code}?tv=1`);
  await sleep(1500);
  await host.page.locator("#classics-h").scrollIntoViewIfNeeded();
  if (!ONLY.length) await shot("lobby", "classics", "The lobby: the new Classics section", [...players, tv]);
  const games = { truthdare: truthOrDare, wordrace: wordRace, lastcard: lastCard, ludo };
  for (const [id, fn] of Object.entries(games)) {
    if (ONLY.length && !ONLY.includes(id)) continue;
    const t0 = Date.now();
    try {
      await fn(players, tv, host);
      console.log("done", id, Math.round((Date.now() - t0) / 1000) + "s");
    } catch (e) {
      console.log("FAILED", id, e.message);
      await shot(id, "failure", "Where the capture stopped", [...players, tv], { wait: 200 });
      await toLobby(host);
    }
  }
  await browser.close();
  console.log("shots", shots.length);
})();

// Dev tool (not production). Run from frontend/ with the API on :8000 (JUMPSCARE=false) and web on :5173:
//   node ../docs/handoff/tools/sweep.cjs <out dir> [game ids...]
// A "monkey" end-to-end sweep of every game on real screens: four seated players (laptop 1366 light,
// phone 390 dark, small phone 320 light, tablet 820 dark) and a TV. Each step one player clicks a random
// control the game offers (text boxes get a word), and the host skips waits now and then, so every game
// runs from intro to results. On every new phase on every screen: a screenshot plus checks for page
// overflow, clipped text, and words too wide for their box (they'd split mid-word). JS errors are
// collected throughout; axe runs at the start and at the results. Prints a summary per game and writes
// summary.json.
const fs = require("fs");
const path = require("path");
const { chromium } = require(path.resolve(__dirname, "../../../frontend/node_modules/@playwright/test"));
const OUT = process.argv[2];
const ONLY = process.argv.slice(3);
const BASE = "http://localhost:5173";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
fs.mkdirSync(OUT, { recursive: true });

const GAMES = [
  "frenemy", "alibi", "price", "telepathy", "mural", "blackjack", "crossword", "dice", "split", "chicken", "wits",
  "codes", "roulette", "lonely", "boxes", "codewords", "truthdare", "wordrace", "lastcard", "ludo", "chess",
  "drawguess", "telephone", "tycoon",
];
const SKIP_NAMES = /How to play|Sign in|Sound|mode|Leave|Skip wait|End the|Tap again|bankruptcy|Call it a night|Keep playing|Propose a trade|Withdraw|Decline|Back to|Play another|Play again|Copy|TV|Kick|Lock/i;
const WORDS = ["crane", "pizza", "a happy dog", "slate", "house", "banana", "moon", "rocket"];
const MAX_STEPS = 180;

(async () => {
  const b = await chromium.launch();
  const errors = [];
  const open = async (key, name, w, h, theme, mobile) => {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile, colorScheme: theme });
    await ctx.addInitScript((t) => localStorage.setItem("snazzlebop:theme", t), theme);
    const page = await ctx.newPage();
    page.on("dialog", (d) => d.accept().catch(() => undefined));
    page.on("pageerror", (e) => errors.push({ key, error: String(e.stack || e.message || e).split(/\n/).slice(0, 3).join(" | ").slice(0, 300) }));
    page.on("console", (m) => {
      if (m.type() !== "error") return;
      const t = m.text();
      if (/WebSocket|DevTools|Failed to load resource|ERR_/.test(t)) return;
      errors.push({ key, error: t.slice(0, 200) });
    });
    return { key, name, page };
  };
  const host = await open("laptop", "Ana", 1366, 768, "light", false);
  const phone = await open("phone", "Bartholomew X", 390, 844, "dark", true);
  const small = await open("small", "Alexandria Wood", 320, 640, "light", true);
  const tablet = await open("tablet", "Zara", 820, 1180, "dark", true);
  const players = [host, phone, small, tablet];
  await host.page.goto(BASE);
  await host.page.locator("#host-name").fill(host.name);
  await host.page.locator("#host-name").press("Enter");
  await host.page.waitForURL(/\/r\/[A-Z]+/);
  const code = /\/r\/([A-Z]+)/.exec(host.page.url())[1];
  for (const p of [phone, small, tablet]) {
    await p.page.goto(`${BASE}/r/${code}`);
    await p.page.locator("#join-name").fill(p.name);
    await p.page.getByRole("button", { name: /Join as a contestant/ }).click();
    await p.page.waitForSelector(".contestants");
  }
  const tv = await open("tv", "", 1920, 1080, "dark", false);
  await tv.page.goto(`${BASE}/r/${code}?tv=1`);
  const screens = [...players, tv];

  const check = async (p) =>
    p.page.evaluate(() => {
      const out = [];
      const doc = document.documentElement;
      if (doc.scrollWidth > doc.clientWidth + 1) out.push(`page overflows by ${doc.scrollWidth - doc.clientWidth}px`);
      const seen = new Set();
      for (const el of document.querySelectorAll("button, .chip, .sign-part, .sign, h2, h3, .score-pts, .ty-cash")) {
        const r = el.getBoundingClientRect();
        if (!r.width || getComputedStyle(el).visibility === "hidden" || el.closest("[aria-hidden='true']")) continue;
        const text = (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40);
        if (!text) continue;
        if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX !== "visible") out.push(`clipped: "${text}"`);
        // A single word wider than its box would be split mid-word (or overflow). Only visible text
        // counts (screen-reader-only spans are 1px wide), and only words with letters (not emoji).
        const style = getComputedStyle(el);
        const room = el.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          const parent = node.parentElement;
          if (!parent || parent.getBoundingClientRect().width < 3) continue;
          const probe = document.createElement("span");
          probe.style.whiteSpace = "nowrap";
          probe.style.position = "absolute";
          probe.style.visibility = "hidden";
          parent.appendChild(probe);
          for (const word of (node.textContent || "").split(/\s+/)) {
            if (!/\p{L}{2}/u.test(word) || seen.has(word)) continue;
            probe.textContent = word;
            if (probe.getBoundingClientRect().width > room + 1) {
              seen.add(word);
              out.push(`word too wide: "${word}" in "${text}"`);
            }
          }
          probe.remove();
        }
      }
      return out;
    });
  const axe = async (p) => {
    await p.page.addScriptTag({ path: path.resolve(__dirname, "../../../frontend/node_modules/axe-core/axe.min.js") }).catch(() => undefined);
    return p.page
      .evaluate(async () => {
        const res = await window.axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] });
        return res.violations.map((v) => `${v.id}: ${v.nodes[0]?.target}`);
      })
      .catch(() => ["axe failed to run"]);
  };
  const sign = async (p) => ((await p.page.locator(".show-head .sign").first().textContent({ timeout: 300 }).catch(() => "")) || "").trim();
  const atResults = async () =>
    (await host.page.getByRole("button", { name: /Play another game/ }).count()) > 0;

  const summary = {};
  for (const id of ONLY.length ? ONLY : GAMES) {
    const dir = path.join(OUT, id);
    fs.mkdirSync(dir, { recursive: true });
    const issues = new Set();
    const before = errors.length;
    const phases = {};
    let shotNo = 0;
    const capture = async (p, why) => {
      const s = await sign(p);
      const k = `${p.key}:${s}`;
      if (phases[k] && why !== "force") return;
      phases[k] = true;
      shotNo++;
      await p.page.screenshot({ path: path.join(dir, `${String(shotNo).padStart(3, "0")}-${p.key}.jpg`), type: "jpeg", quality: 60 }).catch(() => undefined);
      for (const i of await check(p).catch(() => [])) issues.add(`${p.key}: ${i}`);
    };
    // start
    // The tile with a plain "Start!" (team games also have a "Start in teams" tile).
    const tile = host.page.locator(`article.seg-${id}`).filter({ has: host.page.getByRole("button", { name: /^Start!/ }) }).first();
    if (!(await tile.count())) {
      summary[id] = { error: "no lobby tile" };
      console.log(id, "NO TILE");
      continue;
    }
    await tile.scrollIntoViewIfNeeded();
    await tile.getByRole("button", { name: /^Start!/ }).first().click();
    await sleep(1500);
    for (const p of players) await p.page.getByRole("button", { name: /I’m ready/ }).click({ timeout: 2500 }).catch(() => undefined);
    await sleep(1200);
    for (const p of screens) await capture(p, "force");
    for (const v of await axe(small)) issues.add(`small axe: ${v}`);
    let steps = 0;
    let finished = false;
    for (; steps < MAX_STEPS; steps++) {
      if (await atResults()) {
        finished = true;
        break;
      }
      const p = players[Math.floor(Math.random() * players.length)];
      // type into a visible text box now and then
      const box = p.page.locator(`[class*="seg-${id}"] input[type="text"]:visible, [class*="seg-${id}"] input:not([type]):visible`).first();
      if ((await box.count()) && Math.random() < 0.5) {
        await box.fill(WORDS[Math.floor(Math.random() * WORDS.length)]).catch(() => undefined);
        await box.press("Enter").catch(() => undefined);
      } else {
        const buttons = p.page.locator(`[class*="seg-${id}"] button:visible:enabled, .ready-bar button:visible:enabled`);
        const n = await buttons.count();
        const choices = [];
        for (let i = 0; i < n; i++) {
          const label = ((await buttons.nth(i).getAttribute("aria-label").catch(() => "")) || (await buttons.nth(i).textContent().catch(() => "")) || "").trim();
          if (!SKIP_NAMES.test(label)) choices.push(i);
        }
        if (choices.length) await buttons.nth(choices[Math.floor(Math.random() * choices.length)]).click({ timeout: 2000 }).catch(() => undefined);
      }
      await sleep(250);
      if (steps % 4 === 3) await host.page.getByRole("button", { name: /Skip wait/ }).click({ timeout: 1500 }).catch(() => undefined);
      await sleep(250);
      for (const s of screens) await capture(s);
    }
    if (finished) {
      await sleep(1500);
      for (const p of screens) await capture(p, "force");
      for (const v of await axe(phone)) issues.add(`phone axe (results): ${v}`);
      await host.page.getByRole("button", { name: /Play another game/ }).click();
    } else {
      await host.page.getByRole("button", { name: /End the/ }).click({ timeout: 2000 }).catch(() => undefined);
      await host.page.getByRole("button", { name: /Tap again/ }).click({ timeout: 2000 }).catch(() => undefined);
    }
    await sleep(1500);
    const errs = errors.slice(before).map((e) => `${e.key}: ${e.error}`);
    summary[id] = { finished, steps, phases: Object.keys(phases).length, issues: [...issues], errors: errs };
    console.log(`${finished ? "OK " : "DNF"} ${id}: ${steps} steps, ${Object.keys(phases).length} phase screens, ${issues.size} issues, ${errs.length} errors`);
    for (const i of issues) console.log("    -", i);
    for (const e of errs) console.log("    !", e);
  }
  fs.writeFileSync(path.join(OUT, "summary.json"), JSON.stringify(summary, null, 1));
  await b.close();
})();

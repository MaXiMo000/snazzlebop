// Dev tool (not production). Run from frontend/: node ../docs/handoff/tools/drawguess_capture.cjs <out dir>
// Draw & Guess on real screens: five players and a TV. The artist draws a house with the mouse/finger,
// the others guess (wrong, close, right), one guesser reloads mid-drawing (the canvas must come back),
// then the host skips to the final scores.
const path = require("path");
const fs = require("fs");
const { chromium } = require(path.resolve(__dirname, "../../../frontend/node_modules/@playwright/test"));
const OUT = process.argv[2];
fs.mkdirSync(OUT, { recursive: true });
const BASE = "http://localhost:5173";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const b = await chromium.launch();
  const open = async (key, name, w, h, theme, mobile) => {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile, colorScheme: theme });
    await ctx.addInitScript((t) => localStorage.setItem("snazzlebop:theme", t), theme);
    return { key, name, page: await ctx.newPage() };
  };
  const host = await open("laptop", "Ana", 1366, 768, "light", false);
  const phone = await open("phone", "Bartholomew X", 390, 844, "dark", true);
  const small = await open("small", "Alexandria Wood", 320, 640, "light", true);
  const mid = await open("mid", "Zara", 360, 740, "dark", true);
  const tablet = await open("tablet", "Theo", 820, 1180, "light", true);
  await host.page.goto(BASE);
  await host.page.locator("#host-name").fill(host.name);
  await host.page.locator("#host-name").press("Enter");
  await host.page.waitForURL(/\/r\/[A-Z]+/);
  const code = /\/r\/([A-Z]+)/.exec(host.page.url())[1];
  const join = async (p) => {
    await p.page.goto(`${BASE}/r/${code}`);
    await p.page.locator("#join-name").fill(p.name);
    await p.page.getByRole("button", { name: /Join as a contestant/ }).click();
    await p.page.waitForSelector(".contestants");
  };
  for (const p of [phone, small, mid, tablet]) await join(p);
  const tv = await open("tv", "", 1920, 1080, "dark", false);
  await tv.page.goto(`${BASE}/r/${code}?tv=1`);
  const players = [host, phone, small, mid, tablet];
  const shot = async (step, who, full = true) => {
    await sleep(900);
    for (const p of who) await p.page.screenshot({ path: path.join(OUT, `${step}-${p.key}.png`), fullPage: full && p.key !== "tv" });
  };
  const sign = async (p) => (await p.page.locator(".show-head .sign").first().textContent().catch(() => "")) || "";
  const artist = async () => {
    for (let i = 0; i < 40; i++) {
      for (const p of players) if ((await sign(p)).includes("Your turn to draw") || (await sign(p)).includes("Draw it")) return p;
      await sleep(250);
    }
    throw new Error("no artist");
  };
  const axe = async (p, label) => {
    await p.page.addScriptTag({ path: path.resolve(__dirname, "../../../frontend/node_modules/axe-core/axe.min.js") });
    const r = await p.page.evaluate(async () => {
      const res = await window.axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] });
      return res.violations.map((v) => `${v.id}: ${v.nodes.length} ${v.nodes[0]?.target}`);
    });
    console.log("axe", label, JSON.stringify(r));
  };
  const overflow = async (p) =>
    p.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  // Strokes in canvas units (800 x 600).
  const stroke = async (p, pts) => {
    await p.page.locator(".dg-canvas").scrollIntoViewIfNeeded();
    const box = await p.page.locator(".dg-canvas").boundingBox();
    const at = ([x, y]) => [box.x + (x / 800) * box.width, box.y + (y / 600) * box.height];
    await p.page.mouse.move(...at(pts[0]));
    await p.page.mouse.down();
    for (const pt of pts.slice(1)) await p.page.mouse.move(...at(pt), { steps: 8 });
    await p.page.mouse.up();
    await sleep(120);
  };
  const pick = async (p, label) => p.page.getByRole("button", { name: label, exact: true }).click();
  const inked = async (p) =>
    p.page.evaluate(() => {
      const c = document.querySelector(".dg-canvas");
      const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 0; i < d.length; i += 16) if (d[i] < 200) n++;
      return n;
    });

  const tile = host.page.locator("#classics-h").locator("xpath=ancestor::section[1]").locator("article.seg-drawguess");
  await tile.scrollIntoViewIfNeeded();
  await tile.getByRole("button", { name: /^Start!/ }).click();
  await sleep(1500);
  await shot("intro", [phone, small, tv]);
  for (const p of players) await p.page.getByRole("button", { name: /I’m ready/ }).click({ timeout: 4000 }).catch(() => undefined);
  await sleep(1500);

  // -- turn 1: choose ----------------------------------------------------------------------------------
  let a = await artist();
  const others = () => players.filter((p) => p !== a);
  console.log("artist", a.key);
  await shot("choose", [a, others()[0], tv], false);
  const word = (await a.page.locator(".dg-choices .btn").first().textContent()).trim();
  console.log("word", word);
  await a.page.locator(".dg-choices .btn").first().click();
  await a.page.locator(".dg-canvas").waitFor();
  await sleep(600);

  // -- draw a house -------------------------------------------------------------------------------------
  await pick(a, "Thick");
  await stroke(a, [[250, 300], [550, 300], [550, 520], [250, 520], [250, 300]]);
  await pick(a, "Red");
  await stroke(a, [[230, 310], [400, 150], [570, 310]]);
  await pick(a, "Brown");
  await pick(a, "Huge");
  await stroke(a, [[400, 520], [400, 430]]);
  await pick(a, "Yellow");
  await stroke(a, [[680, 90], [700, 100], [690, 120], [670, 110], [680, 90]]);
  await pick(a, "Green");
  await pick(a, "Medium");
  await stroke(a, [[20, 560], [780, 560]]);
  await pick(a, "Blue");
  await stroke(a, [[100, 100], [160, 80]]);
  await a.page.getByRole("button", { name: /Undo/ }).click();
  await sleep(1200);
  console.log("artist inked", await inked(a), "tv inked", await inked(tv));
  const [g1, g2, g3, g4] = others();
  // A late screen: reload mid-drawing, the drawing must come back.
  await g4.page.reload();
  await g4.page.locator(".dg-canvas").waitFor();
  await sleep(1500);
  console.log("reloaded inked", g4.key, await inked(g4));
  const guess = async (p, text) => {
    await p.page.locator("#dg-guess").fill(text);
    await p.page.locator("#dg-guess").press("Enter");
    await sleep(500);
  };
  await guess(g1, "a big dinosaur?");
  await guess(g2, word.length >= 4 ? word.slice(0, -1) : "zzzz");
  await guess(g3, "maybe a castle");
  await shot("draw", [a, g1, g2, g3, g4, tv], false);
  await shot("draw-full", [a, g2, small]);
  await axe(a, "artist");
  await axe(g2, "guesser");
  await guess(g1, word);
  await sleep(800);
  await shot("guessed", [g1, g2, tv], false);
  for (const p of players) console.log("overflow", p.key, await overflow(p));
  // On a laptop the whole canvas (and the artist's tools) must fit the first screen.
  for (const sel of [".dg-paper", ".dg-tools"]) {
    const box = await host.page.evaluate((q) => {
      const e = document.querySelector(q);
      return e ? Math.round(e.getBoundingClientRect().bottom + window.scrollY) : null;
    }, sel);
    console.log("laptop bottom", sel, box, "of", 768);
  }

  // -- reveal --------------------------------------------------------------------------------------------
  const skipBtn = host.page.getByRole("button", { name: /Skip wait/ });
  await skipBtn.click();
  await sleep(1200);
  await shot("reveal", [a, g2, small, tv], false);

  // -- through to the end ------------------------------------------------------------------------------
  for (let i = 0; i < 60; i++) {
    if ((await sign(host)).includes("Final scores")) break;
    await skipBtn.click({ timeout: 3000 }).catch(() => undefined);
    await sleep(700);
  }
  await sleep(2500);
  await shot("final", [host, phone, small, tv], false);
  await shot("final-full", [phone, small]);
  await b.close();
  console.log("done", code);
})();

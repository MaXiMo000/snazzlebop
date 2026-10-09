// Dev tool (not production). Run from frontend/: node ../docs/handoff/tools/telephone_capture.cjs <out dir>
// Draw Telephone on real screens: five players (320/360/390 phones, tablet, laptop) and a TV play a whole
// game: write, draw (one artist reloads mid-drawing: their drawing must come back), describe, draw,
// describe, then the album with likes, then the final books. Screenshots of every phase, axe, overflow.
const path = require("path");
const fs = require("fs");
const { chromium } = require(path.resolve(__dirname, "../../../frontend/node_modules/@playwright/test"));
const OUT = process.argv[2];
fs.mkdirSync(OUT, { recursive: true });
const BASE = "http://localhost:5173";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const SENTENCES = [
  "A cat running for president",
  "A shark at the dentist",
  "Grandma winning a breakdance battle",
  "A snowman on a beach holiday",
  "A dragon afraid of the dark",
];

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
  const axe = async (p, label) => {
    await p.page.addScriptTag({ path: path.resolve(__dirname, "../../../frontend/node_modules/axe-core/axe.min.js") });
    const r = await p.page.evaluate(async () => {
      const res = await window.axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] });
      return res.violations.map((v) => `${v.id}: ${v.nodes.length} ${v.nodes[0]?.target}`);
    });
    console.log("axe", label, JSON.stringify(r));
  };
  const overflow = async () => {
    for (const p of players) {
      const o = await p.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      if (o) console.log("OVERFLOW", p.key, o);
    }
  };
  const inked = async (p) =>
    p.page.evaluate(() => {
      const c = document.querySelector(".dg-canvas");
      if (!c) return -1;
      const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 0; i < d.length; i += 16) if (d[i] < 200) n++;
      return n;
    });
  const stroke = async (p, pts) => {
    const canvas = p.page.locator(".dg-canvas").first();
    await canvas.scrollIntoViewIfNeeded();
    const box = await canvas.boundingBox();
    const at = ([x, y]) => [box.x + (x / 800) * box.width, box.y + (y / 600) * box.height];
    await p.page.mouse.move(...at(pts[0]));
    await p.page.mouse.down();
    for (const pt of pts.slice(1)) await p.page.mouse.move(...at(pt), { steps: 8 });
    await p.page.mouse.up();
    await sleep(150);
  };
  const doodle = async (p, i) => {
    await stroke(p, [[200 + i * 20, 150], [600, 150], [600, 450], [200, 450], [200 + i * 20, 150]]);
    await p.page.getByRole("button", { name: "Red", exact: true }).click();
    await stroke(p, [[300, 300], [400, 220 + i * 10], [500, 300]]);
  };
  const phase = async () => (await host.page.locator(".show-head .sign").first().textContent()) || "";

  const tile = host.page.locator("#classics-h").locator("xpath=ancestor::section[1]").locator("article.seg-telephone");
  await tile.scrollIntoViewIfNeeded();
  await tile.getByRole("button", { name: /^Start!/ }).click();
  await sleep(1500);
  await shot("intro", [phone, tv]);
  for (const p of players) await p.page.getByRole("button", { name: /I’m ready/ }).click({ timeout: 4000 }).catch(() => undefined);
  await sleep(1500);

  // -- write -------------------------------------------------------------------------------------------
  await shot("write", [phone, small, tv], false);
  await axe(phone, "write");
  await small.page.getByRole("button", { name: /Use it/ }).click();
  for (const [i, p] of players.entries()) {
    if (p !== small) await p.page.locator("#tp-text").fill(SENTENCES[i]);
    if (p === tablet) continue;
    await p.page.locator("#tp-text").press("Enter");
    await sleep(300);
  }
  await shot("write-sent", [phone, tv], false);
  await tablet.page.locator("#tp-text").press("Enter");
  await sleep(1500);

  // -- draw ---------------------------------------------------------------------------------------------
  for (const [i, p] of players.entries()) await doodle(p, i);
  await mid.page.reload(); // an artist's phone reloads mid-drawing
  await mid.page.locator(".dg-canvas").waitFor();
  await sleep(2000);
  console.log("reloaded artist's canvas inked:", await inked(mid), "(should be > 0)");
  await shot("draw", [host, phone, small, tv], false);
  await shot("draw-full", [small]);
  await axe(phone, "draw");
  await overflow();
  for (const p of players) {
    await p.page.getByRole("button", { name: /I’m done/ }).click();
    await sleep(250);
  }
  await sleep(1500);

  // -- describe --------------------------------------------------------------------------------------------
  await sleep(1500);
  console.log("describe drawings inked:", await inked(phone), await inked(small));
  await shot("describe", [phone, small, host, tv], false);
  await axe(small, "describe");
  for (const [i, p] of players.entries()) {
    await p.page.locator("#tp-text").fill(["a house on fire", "a box with a smile", "a red tent", "a happy cake", "a sad window"][i]);
    await p.page.locator("#tp-text").press("Enter");
    await sleep(300);
  }
  await sleep(1500);
  // -- draw again, then describe again ----------------------------------------------------------------------
  for (const [i, p] of players.entries()) {
    await doodle(p, i + 2);
    await p.page.getByRole("button", { name: /I’m done/ }).click();
    await sleep(250);
  }
  await sleep(2500);
  for (const p of players) {
    await p.page.locator("#tp-text").fill("no idea, honestly");
    await p.page.locator("#tp-text").press("Enter");
    await sleep(300);
  }
  await sleep(2000);
  console.log("phase now:", await phase());

  // -- album --------------------------------------------------------------------------------------------
  const skip = host.page.getByRole("button", { name: /Skip wait/ });
  for (let i = 0; i < 3; i++) {
    await skip.click();
    await sleep(900);
  }
  await sleep(3000); // the newest drawing replays
  const like = phone.page.locator(".tp-like").first();
  if (await like.count()) await like.click();
  await sleep(800);
  await shot("album", [phone, small, host, tv], false);
  await shot("album-full", [phone]);
  await axe(phone, "album");
  await overflow();
  for (let i = 0; i < 40; i++) {
    if ((await phase()).includes("Final scores")) break;
    await skip.click({ timeout: 3000 }).catch(() => undefined);
    await sleep(600);
  }
  await sleep(2500);
  await shot("final", [host, phone, small, tv], false);
  await shot("final-full", [phone, small]);
  await axe(phone, "final");
  await overflow();
  await b.close();
  console.log("done", code);
})();

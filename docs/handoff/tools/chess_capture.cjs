// Dev tool (not production). Run from frontend/: node ../docs/handoff/tools/chess_capture.cjs <out dir> [args]
// Chess on real screens: 1 v 1 (Scholar's Mate) then 2 v 2 teams with a suggestion arrow.
const path = require("path");
const fs = require("fs");
const { chromium } = require(require("path").resolve(__dirname, "../../../frontend/node_modules/@playwright/test"));
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
  await join(phone);
  const tv = await open("tv", "", 1920, 1080, "dark", false);
  await tv.page.goto(`${BASE}/r/${code}?tv=1`);
  const shot = async (step, who, full = true) => {
    await sleep(800);
    for (const p of who) await p.page.screenshot({ path: path.join(OUT, `${step}-${p.key}.png`), fullPage: full && p.key !== "tv" });
  };
  const players = [host, phone];
  const mover = async () => {
    for (let i = 0; i < 40; i++) {
      for (const p of players) if (((await p.page.locator(".show-head .sign").first().textContent().catch(() => "")) || "").includes("Your move")) return p;
      await sleep(250);
    }
    throw new Error("nobody to move");
  };
  const move = async (uci, snap) => {
    const p = await mover();
    await p.page.locator(`.cs-sq[aria-label^="${uci.slice(0, 2)}"]`).click();
    if (snap) await shot(snap, [p], false);
    await p.page.locator(`.cs-sq[aria-label^="${uci.slice(2, 4)}"]`).click();
    await sleep(700);
  };

  // -- 1 v 1 ----------------------------------------------------------------------------------------
  const tile = host.page.locator("#classics-h").locator("xpath=ancestor::section[1]").locator("article.seg-chess");
  await tile.scrollIntoViewIfNeeded();
  await tile.getByRole("button", { name: /^Start!/ }).click();
  await sleep(1500);
  await shot("intro", [phone, tv]);
  for (const p of players) await p.page.getByRole("button", { name: /I’m ready/ }).click({ timeout: 4000 }).catch(() => undefined);
  await host.page.locator(".cs-board").waitFor();
  await shot("start", [host, phone, tv], false);
  await phone.page.addScriptTag({ path: require("path").resolve(__dirname, "../../../frontend/node_modules/axe-core/axe.min.js") });
  const axe = await phone.page.evaluate(async () => {
    const r = await window.axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] });
    return r.violations.map((v) => `${v.id}: ${v.nodes.length} ${v.nodes[0]?.target}`);
  });
  console.log("axe", JSON.stringify(axe));
  const sizes = await phone.page.evaluate(() => [...document.querySelectorAll(".cs-sq")].slice(0, 1).map((e) => Math.round(e.getBoundingClientRect().width)));
  console.log("square", sizes);
  await move("e2e4", "pick");
  await move("e7e5");
  await move("f1c4");
  await move("b8c6");
  await move("d1h5");
  await shot("mid", [host, phone, tv], false);
  await move("g8f6");
  await move("h5f7");
  await sleep(2500);
  await shot("mate", [host, phone, tv], false);
  await shot("mate-full", [phone]);
  await host.page.getByRole("button", { name: /Play another game/ }).click({ timeout: 10000 }).catch(() => undefined);
  await sleep(1500);

  // -- 2 v 2 ----------------------------------------------------------------------------------------
  const small = await open("small", "Alexandria Wood", 320, 640, "light", true);
  const tablet = await open("tablet", "Zara", 820, 1180, "dark", true);
  await join(small);
  await join(tablet);
  const team = host.page.locator("#team-games-h").locator("xpath=ancestor::section[1]").locator("article.seg-chess");
  await team.scrollIntoViewIfNeeded();
  await team.getByRole("button", { name: /Start in teams/ }).click();
  await sleep(1500);
  const four = [host, phone, small, tablet];
  for (const p of four) await p.page.getByRole("button", { name: /I’m ready/ }).click({ timeout: 4000 }).catch(() => undefined);
  await host.page.locator(".cs-board").waitFor();
  await sleep(1000);
  // The non-mover on the side to move suggests a move; then shoot the mover with the arrow.
  let m = null;
  let mate = null;
  for (const p of four) {
    const sign = (await p.page.locator(".show-head .sign").first().textContent()) || "";
    if (sign.includes("Your move")) m = p;
    else if (sign.includes("suggest one")) mate = p;
  }
  if (mate) {
    for (const sqName of ["d2", "d7"]) {
      await mate.page.locator(`.cs-sq[aria-label^="${sqName}"]`).click();
      if ((await mate.page.locator(".cs-sq.target").count()) > 0) break;
    }
    await shot("team-suggesting", [mate], false);
    const target = (await mate.page.locator('.cs-sq.target').first().getAttribute("aria-label")) || "";
    await mate.page.locator(".cs-sq.target").last().click();
    await sleep(800);
    console.log("suggested", target);
  }
  await shot("team", [...four, tv], false);
  await shot("team-full", [small, phone]);
  await b.close();
  console.log("done", code);
})();

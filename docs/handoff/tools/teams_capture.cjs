// Dev tool (not production). Run from frontend/: node ../docs/handoff/tools/teams_capture.cjs <out dir> [args]
// Team mode on real screens: lobby (Team games), the intro's teams + shuffle, the in-game badge, the result.
const path = require("path");
const fs = require("fs");
const { chromium } = require(require("path").resolve(__dirname, "../../../frontend/node_modules/@playwright/test"));
const OUT = process.argv[2];
fs.mkdirSync(OUT, { recursive: true });
const BASE = "http://localhost:5173";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const DEV = [
  ["laptop", "Ana", 1366, 768, "light", false],
  ["phone", "Bartholomew X", 390, 844, "dark", true],
  ["small", "Alexandria Wood", 320, 640, "light", true],
  ["tablet", "Zara", 820, 1180, "dark", true],
];

(async () => {
  const b = await chromium.launch();
  const open = async ([key, name, w, h, theme, mobile]) => {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile, colorScheme: theme });
    await ctx.addInitScript((t) => localStorage.setItem("snazzlebop:theme", t), theme);
    return { key, name, page: await ctx.newPage() };
  };
  const ps = [];
  for (const d of DEV) ps.push(await open(d));
  const host = ps[0];
  await host.page.goto(BASE);
  await host.page.locator("#host-name").fill(host.name);
  await host.page.locator("#host-name").press("Enter");
  await host.page.waitForURL(/\/r\/[A-Z]+/);
  const code = /\/r\/([A-Z]+)/.exec(host.page.url())[1];
  for (const p of ps.slice(1)) {
    await p.page.goto(`${BASE}/r/${code}`);
    await p.page.locator("#join-name").fill(p.name);
    await p.page.getByRole("button", { name: /Join as a contestant/ }).click();
    await p.page.waitForSelector(".contestants");
  }
  const tv = await open(["tv", "", 1920, 1080, "dark", false]);
  await tv.page.goto(`${BASE}/r/${code}?tv=1`);
  const all = [...ps, tv];
  const shot = async (step, who, full = true) => {
    await sleep(700);
    for (const p of who) await p.page.screenshot({ path: path.join(OUT, `${step}-${p.key}.png`), fullPage: full && p.key !== "tv" });
  };

  const section = host.page.locator("#team-games-h").locator("xpath=ancestor::section[1]");
  await section.scrollIntoViewIfNeeded();
  await sleep(500);
  await section.screenshot({ path: path.join(OUT, "lobby-teams-laptop.png") });
  const tile = section.locator("article.seg-truthdare");
  await tile.locator("#team-opt-truthdare-length").click();
  await host.page.getByRole("option", { name: /Quick/ }).click();
  await tile.getByRole("button", { name: /Start in teams/ }).click();
  await host.page.locator("#teams-h").waitFor();
  await shot("intro", all);
  await host.page.getByRole("button", { name: /Shuffle the teams/ }).click();
  await shot("intro-shuffled", [ps[1], tv], true);
  for (const p of ps) await p.page.getByRole("button", { name: /I’m ready/ }).click({ timeout: 4000 }).catch(() => undefined);
  await sleep(1500);
  await shot("game", all, false);
  for (let i = 0; i < 300; i++) {
    if (await host.page.locator(".team-result").isVisible().catch(() => false)) break;
    for (const p of ps) {
      await p.page.locator(".tod-door.truth").click({ timeout: 200, force: true }).catch(() => undefined);
      await p.page.getByRole("button", { name: /Judge me/ }).click({ timeout: 200 }).catch(() => undefined);
      await p.page.getByRole("button", { name: /Nailed it/ }).click({ timeout: 200 }).catch(() => undefined);
    }
    await host.page.getByRole("button", { name: /Skip wait/ }).click({ timeout: 200 }).catch(() => undefined);
    await sleep(300);
  }
  await sleep(2500);
  for (const p of all) await p.page.locator(".team-result").scrollIntoViewIfNeeded().catch(() => undefined);
  await shot("result", all, false);
  await shot("result-full", ps.slice(1, 3));
  await b.close();
  console.log("done", code);
})();

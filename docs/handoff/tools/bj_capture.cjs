// Dev tool (not production). Run from frontend/: node ../docs/handoff/tools/bj_capture.cjs <out dir> [args]
// One Blackjack hand with a laptop host and two phones; screenshots the phones' real viewport on their
// turn (is Hit/Stand in reach without scrolling?) and at the payout.  node bj.cjs <out dir>
const path = require("path");
const fs = require("fs");
const { chromium } = require(require("path").resolve(__dirname, "../../../frontend/node_modules/@playwright/test"));
const OUT = process.argv[2];
fs.mkdirSync(OUT, { recursive: true });
const BASE = "http://localhost:5173";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const b = await chromium.launch();
  const open = async (name, w, h, theme, mobile) => {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, isMobile: mobile, hasTouch: mobile, colorScheme: theme });
    await ctx.addInitScript((t) => localStorage.setItem("snazzlebop:theme", t), theme);
    const page = await ctx.newPage();
    return { name, page };
  };
  const host = await open("Ana", 1366, 768, "light", false);
  const phone = await open("Bartholomew X", 390, 844, "dark", true);
  const tiny = await open("Alexandria Wood", 320, 640, "light", true);
  await host.page.goto(BASE);
  await host.page.locator("#host-name").fill(host.name);
  await host.page.locator("#host-name").press("Enter");
  await host.page.waitForURL(/\/r\/[A-Z]+/);
  const code = /\/r\/([A-Z]+)/.exec(host.page.url())[1];
  for (const p of [phone, tiny]) {
    await p.page.goto(`${BASE}/r/${code}`);
    await p.page.locator("#join-name").fill(p.name);
    await p.page.getByRole("button", { name: /Join as a contestant/ }).click();
    await p.page.waitForSelector(".contestants");
  }
  const card = host.page.locator("article.game-card.seg-blackjack");
  await card.scrollIntoViewIfNeeded();
  await card.getByRole("button", { name: /Start!/ }).click();
  const all = [host, phone, tiny];
  await sleep(1500);
  for (const p of all) await p.page.getByRole("button", { name: /I’m ready/ }).click({ timeout: 5000 }).catch(() => undefined);
  for (const p of all) await p.page.locator(".bet-chip").first().click({ timeout: 15000 }).catch(() => undefined);
  const shotDone = new Set();
  for (let i = 0; i < 400; i++) {
    for (const p of [phone, tiny, host]) {
      if (await p.page.locator(".bj-move").isVisible().catch(() => false)) {
        if (!shotDone.has(p.name)) {
          shotDone.add(p.name);
          await p.page.evaluate(() => window.scrollTo(0, 0));
          await sleep(500);
          await p.page.screenshot({ path: path.join(OUT, `turn-${p.page.viewportSize().width}.png`) });
        }
        await p.page.getByRole("button", { name: /^Stand$/ }).click({ timeout: 2000 }).catch(() => undefined);
      }
    }
    if (await phone.page.locator(".bj-my-result").isVisible().catch(() => false)) break;
    await sleep(300);
  }
  await sleep(1500);
  for (const p of [phone, tiny]) {
    await p.page.screenshot({ path: path.join(OUT, `result-${p.page.viewportSize().width}.png`) });
  }
  await host.page.screenshot({ path: path.join(OUT, "result-laptop.png"), fullPage: true });
  await b.close();
  console.log("done", [...shotDone]);
})();

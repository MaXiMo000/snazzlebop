// Dev tool (not production). Run from frontend/: node ../docs/handoff/tools/acct_capture.cjs <out dir> [args]
// Accounts end to end in real browsers: sign up, recovery code, coins (topped up in the dev DB), shop,
// then a signed-in seat in a bot game using a power-up and earning coins.   node acct.cjs <out> <code>
const path = require("path");
const fs = require("fs");
const { execFileSync } = require("child_process");
const { chromium } = require(require("path").resolve(__dirname, "../../../frontend/node_modules/@playwright/test"));
const [OUT, ROOM] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const BASE = "http://localhost:5173";
const REPO = require("path").resolve(__dirname, "../../..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function device(b, w, h, theme, tag) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, colorScheme: theme });
  await ctx.addInitScript((t) => localStorage.setItem("snazzlebop:theme", t), theme);
  const page = await ctx.newPage();
  const shot = async (name, full = true) => page.screenshot({ path: path.join(OUT, `${tag}-${name}.png`), fullPage: full });
  return { page, shot };
}

function topUp(username, coins) {
  const py = `import sqlite3; c=sqlite3.connect(r"${REPO}/snazzlebop.db"); c.execute("update users set coins=? where username_key=?", (${coins}, "${username.toLowerCase()}")); c.commit()`;
  execFileSync(`${REPO}/backend/.venv/Scripts/python.exe`, ["-c", py]);
}

(async () => {
  const b = await chromium.launch();
  const stamp = Date.now().toString(36).slice(-5);
  for (const [w, h, theme, tag] of [[390, 844, "dark", "390"], [320, 640, "light", "320"]]) {
    const { page, shot } = await device(b, w, h, theme, tag);
    const username = `Bartholomew_${tag}${stamp}`.slice(0, 20);
    await page.goto(BASE);
    await sleep(800);
    await shot("home-top", false);
    await page.getByRole("link", { name: "Sign in" }).click();
    await sleep(500);
    await shot("signin");
    await page.getByRole("button", { name: "Sign up" }).click();
    await page.locator("#acct-user").fill(username);
    await page.locator("#acct-pass").fill("party night 2026");
    await shot("signup");
    await page.locator("form").getByRole("button", { name: "Create account" }).click();
    await page.waitForSelector(".acct-code");
    await sleep(400);
    await shot("recovery");
    await page.getByRole("button", { name: "I've saved it" }).click();
    await sleep(800);
    await shot("profile-new");
    topUp(username, 260);
    await page.reload();
    await sleep(1200);
    await page.getByRole("button", { name: /Buy Double Down/ }).click();
    await sleep(500);
    await page.getByRole("button", { name: /Buy Peek/ }).click();
    await sleep(800);
    await shot("profile-shop");
    if (tag === "390" && ROOM) {
      await page.goto(`${BASE}/r/${ROOM}`);
      await page.locator("#join-name").waitFor();
      await sleep(500);
      await shot("join-prefilled", false);
      await page.getByRole("button", { name: /Join as a contestant/ }).click();
      await page.waitForSelector(".contestants");
      fs.writeFileSync(path.join(OUT, "joined.txt"), "1");
      // wait for the bots' host to start the game, then the intro
      for (let i = 0; i < 120; i++) {
        await page.getByRole("button", { name: /I’m ready/ }).click({ timeout: 500 }).catch(() => undefined);
        if (await page.locator(".boost-panel").isVisible().catch(() => false)) break;
        await sleep(500);
      }
      await page.locator(".boost-panel").scrollIntoViewIfNeeded();
      await shot("boost-panel", false);
      await page.locator(".boost-panel").getByRole("button", { name: /Double Down/ }).click();
      await sleep(1200);
      await shot("boost-used", false);
      for (let i = 0; i < 240; i++) {
        if (await page.locator("#coins-news-h").isVisible().catch(() => false)) break;
        const pick = page.locator(".seg-lonely button:not([disabled])").first();
        await pick.click({ timeout: 300 }).catch(() => undefined);
        await sleep(500);
      }
      await page.locator("#coins-news-h").scrollIntoViewIfNeeded().catch(() => undefined);
      await sleep(600);
      await shot("coins-news", false);
      await shot("results-full");
      await page.goto(`${BASE}/account`);
      await sleep(1500);
      await shot("profile-after");
    }
    await page.context().close();
  }
  await b.close();
  console.log("done");
})();

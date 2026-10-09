// Dev tool (not production). Run from frontend/: node ../docs/handoff/tools/chat_capture.cjs <out dir>
// Chat on real screens: four players (laptop, 390, 320, tablet) start Truth or Dare in teams; messages go
// to everyone and to one team; checks the other team never sees team talk, the unread badge, the pop-up,
// the TV ticker, the 320px top bar, axe with the panel open. Screenshots of each.
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
  const overflow = async (p) => p.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  const shot = async (step, who, full = false) => {
    await sleep(600);
    for (const p of who) await p.page.screenshot({ path: path.join(OUT, `${step}-${p.key}.png`), fullPage: full && p.key !== "tv" });
  };
  const say = async (p, text, team = false) => {
    if (!(await p.page.locator(".chat-panel").count())) await p.page.locator(".chat-button").click();
    if (team) await p.page.locator(".chat-tab").nth(1).click();
    else await p.page.locator(".chat-tab").first().click();
    await p.page.locator("#chat-input").fill(text);
    await p.page.locator("#chat-input").press("Enter");
    await sleep(1100);
  };
  const log = async (p) => (await p.page.locator(".chat-log li").allTextContents()).map((s) => s.trim());

  console.log("320 top bar overflow (lobby):", await overflow(small));
  // Lobby: everyone's chat.
  await say(host, "Welcome to game night! 🎉");
  await sleep(500);
  await shot("popup", [phone, small], false);
  console.log("phone badge:", await phone.page.locator(".chat-badge").textContent().catch(() => "none"));
  await say(phone, "Let's goooo");
  await shot("lobby-open", [phone], false);
  await shot("tv-ticker", [tv], false);

  // Team mode: Truth or Dare in teams.
  const team = host.page.locator("#team-games-h").locator("xpath=ancestor::section[1]").locator("article.seg-truthdare");
  await host.page.locator(".chat-close").click().catch(() => undefined);
  await team.scrollIntoViewIfNeeded();
  await team.getByRole("button", { name: /Start in teams/ }).click();
  await sleep(1500);
  for (const p of players) await p.page.getByRole("button", { name: /I’m ready/ }).click({ timeout: 4000 }).catch(() => undefined);
  await sleep(1500);
  // Who's on Ana's team? (her team tab shows the team's name)
  await host.page.locator(".chat-button").click();
  const teamTab = (await host.page.locator(".chat-tab").nth(1).textContent()) || "";
  console.log("Ana's team tab:", teamTab);
  await say(host, "Team secret: pick dare every time", true);
  const seen = {};
  for (const p of players) {
    if (!(await p.page.locator(".chat-panel").count())) await p.page.locator(".chat-button").click();
    const tabs = await p.page.locator(".chat-tab").allTextContents();
    if (tabs.length > 1) await p.page.locator(".chat-tab").nth(1).click();
    await sleep(300);
    seen[p.key] = { tab: tabs[1] ?? "(no team tab)", sawSecret: (await log(p)).some((t) => t.includes("Team secret")) };
  }
  console.log("who saw the team secret:", JSON.stringify(seen));
  const tvText = await tv.page.locator(".chat-ticker").textContent().catch(() => "");
  console.log("TV shows the team secret?", (tvText || "").includes("Team secret"));
  await shot("team", [host, phone, small, tablet], false);
  await phone.page.addScriptTag({ path: path.resolve(__dirname, "../../../frontend/node_modules/axe-core/axe.min.js") });
  const axe = await phone.page.evaluate(async () => (await window.axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] })).violations.map((v) => `${v.id}: ${v.nodes[0]?.target}`));
  console.log("axe (panel open):", JSON.stringify(axe));
  for (const p of players) console.log("overflow", p.key, await overflow(p));
  await b.close();
  console.log("done", code);
})();

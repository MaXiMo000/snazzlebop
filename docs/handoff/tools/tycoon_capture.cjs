// Dev tool (not production). Run from frontend/: node ../docs/handoff/tools/tycoon_capture.cjs <out dir>
// Property Tycoon on real screens.
//  1. Five players (laptop, 390, 320, 360, tablet) + TV: rolling, buying, auctions, a trade between two
//     phones; screenshots of each, axe and overflow checks at every width.
//  2. Two players who buy everything until one owns a whole colour set, then build houses through the UI.
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
  const room = async (host, guests) => {
    await host.page.goto(BASE);
    await host.page.locator("#host-name").fill(host.name);
    await host.page.locator("#host-name").press("Enter");
    await host.page.waitForURL(/\/r\/[A-Z]+/);
    const code = /\/r\/([A-Z]+)/.exec(host.page.url())[1];
    for (const p of guests) {
      await p.page.goto(`${BASE}/r/${code}`);
      await p.page.locator("#join-name").fill(p.name);
      await p.page.getByRole("button", { name: /Join as a contestant/ }).click();
      await p.page.waitForSelector(".contestants");
    }
    return code;
  };
  const start = async (host, everyone) => {
    const tile = host.page.locator("#classics-h").locator("xpath=ancestor::section[1]").locator("article.seg-tycoon");
    await tile.scrollIntoViewIfNeeded();
    await tile.getByRole("button", { name: /^Start!/ }).click();
    await sleep(1500);
    for (const p of everyone) await p.page.getByRole("button", { name: /I’m ready/ }).click({ timeout: 4000 }).catch(() => undefined);
    await host.page.locator(".ty-board").waitFor();
    await sleep(800);
  };
  const shot = async (step, who, full = false) => {
    await sleep(700);
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
  const overflow = async (ps) => {
    for (const p of ps) {
      const o = await p.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      if (o) console.log("OVERFLOW", p.key, o);
    }
  };
  // Every word on the board must fit its square (a word wider than the square would be split).
  const nameFit = async (p) => {
    const bad = await p.page.evaluate(() => {
      const out = [];
      for (const el of document.querySelectorAll(".ty-name")) {
        if (getComputedStyle(el).display === "none") continue;
        const room = el.getBoundingClientRect().width;
        for (const word of el.textContent.split(" ")) {
          const probe = document.createElement("span");
          probe.textContent = word;
          probe.style.whiteSpace = "nowrap";
          el.appendChild(probe);
          const w = probe.getBoundingClientRect().width;
          probe.remove();
          if (w > room + 0.5) out.push(`${word} (${Math.round(w)} > ${Math.round(room)})`);
        }
      }
      return out;
    });
    console.log("board words that don't fit on", p.key, bad.length ? bad.join(", ") : "none");
  };
  const buttons = async (p) => (await p.page.locator(".ty-action button").allTextContents()).map((s) => s.trim());
  const click = async (p, re) => {
    await p.page.locator(".ty-action button").filter({ hasText: re }).first().click();
    await sleep(450);
  };
  /** One move by whoever has something to do. Returns a word for what happened. */
  const step = async (players, host, { buy = true, bidders = [] } = {}) => {
    for (const p of players) {
      const bs = await buttons(p);
      if (bs.some((s) => /Roll/.test(s))) return click(p, /Roll/).then(() => "roll");
      if (bs.some((s) => /^Buy for/.test(s))) {
        if (buy && !(await p.page.locator(".ty-action button").filter({ hasText: /^Buy for/ }).first().isDisabled()))
          return click(p, /^Buy for/).then(() => "buy");
        return click(p, /Auction it/).then(() => "decline");
      }
      if (bs.some((s) => /^Pay \$/.test(s))) {
        const pay = p.page.locator(".ty-action button").filter({ hasText: /^Pay \$/ }).first();
        if (!(await pay.isDisabled())) return click(p, /^Pay \$/).then(() => "pay");
        const m = p.page.locator(".ty-mine button").filter({ hasText: /Mortgage|Sell/ }).first();
        if (await m.count()) return m.click().then(() => sleep(400)).then(() => "raise");
        await click(p, /bankruptcy/);
        return click(p, /Tap again/).then(() => "bankrupt");
      }
      if (bs.some((s) => /End turn/.test(s))) return click(p, /End turn/).then(() => "end");
    }
    // An auction: a couple of bids, then the host closes it.
    const tv = await players[0].page.locator(".ty-action").first().textContent();
    if (/auction/.test(tv || "")) {
      for (const p of bidders) {
        const bid = p.page.locator(".ty-action button").filter({ hasText: /^\$/ }).first();
        const high = Number(((await bid.textContent().catch(() => "")) || "").replace(/[^0-9]/g, "")) || 0;
        if (high < 250 && (await bid.count()) && !(await bid.isDisabled())) {
          await bid.click();
          await sleep(400);
          return "bid";
        }
      }
      await host.page.getByRole("button", { name: /Skip wait/ }).click();
      await sleep(500);
      return "closed";
    }
    await sleep(300);
    return "wait";
  };

  // -- 1. five players and a TV -------------------------------------------------------------------------
  const host = await open("laptop", "Ana", 1366, 768, "light", false);
  const phone = await open("phone", "Bartholomew X", 390, 844, "dark", true);
  const small = await open("small", "Alexandria Wood", 320, 640, "light", true);
  const mid = await open("mid", "Zara", 360, 740, "dark", true);
  const tablet = await open("tablet", "Theo", 820, 1180, "light", true);
  const players = [host, phone, small, mid, tablet];
  const code = await room(host, [phone, small, mid, tablet]);
  const tv = await open("tv", "", 1920, 1080, "dark", false);
  await tv.page.goto(`${BASE}/r/${code}?tv=1`);
  await start(host, players);
  for (const p of [host, tablet, tv]) await nameFit(p);
  await shot("start", [host, phone, small, tv]);
  await axe(phone, "start");
  let shots = { buy: false, auction: false, manage: false };
  for (let i = 0; i < 70; i++) {
    // capture the first of each kind of moment, on every screen
    for (const p of players) {
      const bs = await buttons(p);
      if (!shots.buy && bs.some((s) => /^Buy for/.test(s))) {
        shots.buy = true;
        await shot("buy", [p, tv]);
        await shot("buy-full", [p], true);
        await axe(p, "buy");
      }
    }
    const act = await step(players, host, { buy: i % 5 !== 3, bidders: [phone, small] });
    if (act === "bid" && !shots.auction) {
      shots.auction = true;
      await shot("auction", [phone, small, mid, tv]);
    }
  }
  await shot("mid-game", [host, phone, small, mid, tablet, tv]);
  await shot("mid-game-full", [phone, small], true);
  await overflow(players);
  await axe(small, "mid-game");
  // A trade: the phone offers cash to someone who owns a property, for that property.
  let seller = null;
  let owns = [];
  for (const p of [tablet, mid, small, host]) {
    owns = await p.page.locator(".ty-mine li b").allTextContents();
    if (owns.length) {
      seller = p;
      break;
    }
  }
  seller ??= tablet;
  await phone.page.getByRole("button", { name: /Propose a trade/ }).click();
  await phone.page.locator("#ty-trade-to").click();
  await phone.page.getByRole("option", { name: seller.name }).click();
  if (owns.length) await phone.page.locator(".ty-picks").last().getByText(owns[0]).click();
  await phone.page.locator(".ty-cash-field input").first().fill("120");
  await shot("trade-form", [phone], true);
  await phone.page.getByRole("button", { name: /Send offer/ }).click();
  await sleep(1000);
  await seller.page.locator(".ty-trades").scrollIntoViewIfNeeded();
  await shot("trade-offer", [seller]);
  await seller.page.getByRole("button", { name: /^Accept$/ }).click().catch(() => console.log("no accept button"));
  await sleep(800);
  console.log("traded with", seller.key, "for", owns[0] ?? "nothing", "| phone now owns:", await phone.page.locator(".ty-mine li b").allTextContents());
  // Everyone calls it a night.
  for (const p of players) {
    await p.page.getByRole("button", { name: /Call it a night/ }).click();
    await sleep(400);
  }
  await sleep(2500);
  await shot("final", [host, phone, small, tv]);
  await shot("final-full", [phone], true);
  await overflow(players);

  // -- 2. two players: build houses ---------------------------------------------------------------------
  const a = await open("duo-laptop", "Ana", 1366, 768, "dark", false);
  const z = await open("duo-phone", "Bartholomew X", 390, 844, "light", true);
  await room(a, [z]);
  await start(a, [a, z]);
  let built = false;
  for (let i = 0; i < 400 && !built; i++) {
    for (const p of [a, z]) {
      const build = p.page.locator(".ty-mine button:not([disabled])").filter({ hasText: /\+🏠/ }).first();
      if (await build.count()) {
        for (let k = 0; k < 6 && (await build.count()); k++) {
          await build.click();
          await sleep(500);
        }
        built = true;
        await p.page.locator(".ty-mine").scrollIntoViewIfNeeded();
        await shot("houses", [p, a.key === p.key ? z : a]);
        await shot("houses-full", [p], true);
        break;
      }
    }
    await step([a, z], a, { buy: true });
  }
  console.log("built houses:", built);
  await b.close();
  console.log("done", code);
})();

// Dev tool (not production). Run from frontend/: node ../docs/handoff/tools/ink_touch.cjs <out dir>
// Drawing with a finger on a phone (real touch events through CDP): the stroke must land on the canvas,
// the page must not scroll while drawing, and the laptop watching must get the same line. Saves both
// canvases as PNGs to compare the curve quality.
const path = require("path");
const fs = require("fs");
const { chromium } = require(path.resolve(__dirname, "../../../frontend/node_modules/@playwright/test"));
const OUT = process.argv[2];
fs.mkdirSync(OUT, { recursive: true });
const BASE = "http://localhost:5173";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const b = await chromium.launch();
  const mk = async (w, h, mobile) => {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: mobile ? 3 : 1 });
    return ctx.newPage();
  };
  for (let attempt = 0; attempt < 6; attempt++) {
    const host = await mk(1366, 900, false);
    const phone = await mk(390, 844, true);
    await host.goto(BASE);
    await host.locator("#host-name").fill("Ana");
    await host.locator("#host-name").press("Enter");
    await host.waitForURL(/\/r\/[A-Z]+/);
    const code = /\/r\/([A-Z]+)/.exec(host.url())[1];
    await phone.goto(`${BASE}/r/${code}`);
    await phone.locator("#join-name").fill("Bo");
    await phone.getByRole("button", { name: /Join as a contestant/ }).click();
    await phone.waitForSelector(".contestants");
    const tile = host.locator("article.seg-drawguess").first();
    await tile.scrollIntoViewIfNeeded();
    await tile.getByRole("button", { name: /^Start!/ }).click();
    await sleep(1500);
    for (const p of [host, phone]) await p.getByRole("button", { name: /I’m ready/ }).click({ timeout: 4000 }).catch(() => 0);
    await sleep(1500);
    if (!(await phone.locator(".dg-choices .btn").count())) {
      await host.context().close();
      await phone.context().close();
      continue; // we need the phone to be the artist
    }
    await phone.locator(".dg-choices .btn").first().click();
    const canvas = phone.locator(".dg-canvas");
    await canvas.waitFor();
    await canvas.scrollIntoViewIfNeeded();
    await sleep(600);
    const box = await canvas.boundingBox();
    const cdp = await phone.context().newCDPSession(phone);
    const touch = (type, x, y) =>
      cdp.send("Input.dispatchTouchEvent", { type, touchPoints: type === "touchEnd" ? [] : [{ x, y }] });
    const before = await phone.evaluate(() => window.scrollY);
    // A wavy signature, drawn downwards (a page would scroll if the canvas let it).
    const pts = [];
    for (let i = 0; i <= 120; i++) pts.push([box.x + 20 + (i / 120) * (box.width - 40), box.y + box.height / 2 + Math.sin(i / 8) * box.height * 0.3 + i * 0.4]);
    await touch("touchStart", ...pts[0]);
    for (const pt of pts.slice(1)) {
      await touch("touchMove", ...pt);
      await sleep(10);
    }
    await touch("touchEnd");
    await sleep(1500);
    const after = await phone.evaluate(() => window.scrollY);
    const dark = (p) =>
      p.evaluate(() => {
        const c = document.querySelector(".dg-canvas");
        const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
        let n = 0;
        for (let i = 0; i < d.length; i += 4) if (d[i] < 128) n++;
        return Math.round((n / (c.width * c.height)) * 1000) / 10;
      });
    console.log("page scrolled while drawing:", after - before, "px");
    console.log("ink coverage % phone vs laptop:", await dark(phone), "vs", await dark(host));
    await canvas.screenshot({ path: path.join(OUT, "touch-phone.png") });
    await host.locator(".dg-canvas").screenshot({ path: path.join(OUT, "touch-laptop.png") });
    break;
  }
  await b.close();
})();

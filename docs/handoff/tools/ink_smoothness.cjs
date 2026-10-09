// Dev tool (not production). Run from frontend/: node ../docs/handoff/tools/ink_smoothness.cjs
// How smooth is live drawing? An artist (laptop) scribbles for ~3 s, a guesser watches on a phone with the
// CPU slowed 4x (a budget phone). Reports, for both screens: canvas updates per second while drawing, the
// longest gap between updates, frames over 50 ms (jank), and the delay until the viewer has the whole line.
// Then a big drawing (~15k points) to check that repaints stay cheap as a drawing grows.
const path = require("path");
const { chromium } = require(path.resolve(__dirname, "../../../frontend/node_modules/@playwright/test"));
const BASE = "http://localhost:5173";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const instrument = () => {
  window.__paints = [];
  window.__frames = [];
  const orig = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function (...a) {
    if (this.canvas.classList?.contains("dg-canvas")) window.__paints.push(performance.now());
    return orig.apply(this, a);
  };
  let last = performance.now();
  const tick = (t) => {
    window.__frames.push(t - last);
    last = t;
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
};

const stats = async (page, from, to) =>
  page.evaluate(
    ([from, to]) => {
      const p = window.__paints.filter((t) => t >= from && t <= to);
      const gaps = p.slice(1).map((t, i) => t - p[i]);
      const frames = window.__frames.slice(-Math.round((to - from) / 16));
      return {
        updatesPerSec: Math.round((p.length / (to - from)) * 1000),
        longestGapMs: Math.round(Math.max(0, ...gaps)),
        jankFrames: frames.filter((f) => f > 50).length,
        lastPaint: p.length ? p[p.length - 1] : 0,
      };
    },
    [from, to],
  );

(async () => {
  const b = await chromium.launch();
  const mk = async (w, h, mobile) => {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: mobile ? 2 : 1 });
    await ctx.addInitScript(instrument);
    return ctx.newPage();
  };
  const host = await mk(1366, 900, false);
  const phone = await mk(390, 844, true);
  const cdp = await phone.context().newCDPSession(phone);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
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
  // Make the laptop the artist: whoever has the choices picks; if it's the phone, swap roles.
  await sleep(1500);
  let artist = host;
  let viewer = phone;
  if (!(await host.locator(".dg-choices .btn").count())) {
    console.log("(phone is the artist this time: measuring the laptop as viewer too)");
    artist = phone;
    viewer = host;
  }
  await artist.locator(".dg-choices .btn").first().click();
  await artist.locator(".dg-canvas").waitFor();
  await viewer.locator(".dg-canvas").waitFor();
  await sleep(800);
  const box = await artist.locator(".dg-canvas").boundingBox();
  const at = (x, y) => [box.x + (x / 800) * box.width, box.y + (y / 600) * box.height];

  // ~3 s scribble: a spiral, one mouse event every ~8 ms.
  const t0v = await viewer.evaluate(() => performance.now());
  const t0a = await artist.evaluate(() => performance.now());
  await artist.mouse.move(...at(400, 300));
  await artist.mouse.down();
  for (let i = 0; i < 360; i++) {
    const r = 20 + i * 0.7;
    const a = i / 9;
    await artist.mouse.move(...at(400 + r * Math.cos(a), 300 + r * Math.sin(a) * 0.75));
    await sleep(8);
  }
  await artist.mouse.up();
  const endA = await artist.evaluate(() => performance.now());
  await sleep(2500);
  const endV = await viewer.evaluate(() => performance.now());
  const a = await stats(artist, t0a, endA);
  const v = await stats(viewer, t0v + 300, endV);
  console.log("artist while drawing:", JSON.stringify(a));
  console.log("viewer (4x slower CPU):", JSON.stringify(v));

  // A big drawing: 15k more points in a burst of strokes, then time one repaint on each screen.
  await artist.evaluate(() => 0);
  for (let s = 0; s < 40; s++) {
    await artist.mouse.move(...at(20 + s * 19, 20));
    await artist.mouse.down();
    for (let i = 0; i < 60; i++) await artist.mouse.move(...at(20 + s * 19 + (i % 2) * 15, 20 + i * 9.5));
    await artist.mouse.up();
  }
  await sleep(3000);
  const n = await viewer.evaluate(() => window.__paints.length);
  await artist.mouse.move(...at(700, 500));
  await artist.mouse.down();
  for (let i = 0; i < 40; i++) {
    await artist.mouse.move(...at(700 + i, 500 + (i % 5)));
    await sleep(8);
  }
  await artist.mouse.up();
  const t1 = await artist.evaluate(() => performance.now());
  await sleep(1500);
  const t2 = await viewer.evaluate(() => performance.now());
  console.log("artist, big drawing:", JSON.stringify(await stats(artist, t1 - 400, t1)));
  console.log("viewer, big drawing:", JSON.stringify(await stats(viewer, t2 - 1500, t2)), "paints", (await viewer.evaluate(() => window.__paints.length)) - n);
  const same = await Promise.all(
    [artist, viewer].map((p) =>
      p.evaluate(() => {
        const c = document.querySelector(".dg-canvas");
        const small = document.createElement("canvas");
        small.width = 80;
        small.height = 60;
        small.getContext("2d").drawImage(c, 0, 0, 80, 60);
        const d = small.getContext("2d").getImageData(0, 0, 80, 60).data;
        let dark = 0;
        for (let i = 0; i < d.length; i += 4) if (d[i] < 128) dark++;
        return dark;
      }),
    ),
  );
  console.log("dark pixels (80x60 thumbnail) artist vs viewer:", same.join(" vs "));
  await b.close();
})();

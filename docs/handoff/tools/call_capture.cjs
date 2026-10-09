// Dev tool (not production). Needs a LiveKit server: `livekit-server --dev --bind 127.0.0.1` and the API
// started with LIVEKIT_URL=ws://localhost:7880 LIVEKIT_API_KEY=devkey LIVEKIT_API_SECRET=secret.
//   node ../docs/handoff/tools/call_capture.cjs <out dir>          (run from frontend/)
// A real call with fake cameras and microphones (Chromium's test pattern and beep): three players
// (laptop, 390 phone, 320 phone), one audience member and a TV. Checks that everyone sees everyone,
// video frames and remote audio actually arrive, speaking and mute show for others, the TV gets faces but
// no sound, the big view, leaving; then layout and axe with a game running. Screenshots of each step.
const path = require("path");
const fs = require("fs");
const { chromium } = require(path.resolve(__dirname, "../../../frontend/node_modules/@playwright/test"));
const OUT = process.argv[2];
fs.mkdirSync(OUT, { recursive: true });
const BASE = "http://localhost:5173";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const ok = (what, pass, extra = "") => {
  results.push(pass);
  console.log(`${pass ? "PASS" : "FAIL"} ${what}${extra ? `: ${extra}` : ""}`);
};

(async () => {
  const b = await chromium.launch({
    args: [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      "--autoplay-policy=no-user-gesture-required",
      // speech-like audio (FAKE_AUDIO=path.wav): the default beep is a steady tone that noise suppression removes
      ...(process.env.FAKE_AUDIO ? [`--use-file-for-fake-audio-capture=${process.env.FAKE_AUDIO}`] : []),
    ],
  });
  const open = async (key, name, w, h, theme, mobile) => {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile, colorScheme: theme, permissions: ["camera", "microphone"] });
    await ctx.addInitScript((t) => localStorage.setItem("snazzlebop:theme", t), theme);
    const page = await ctx.newPage();
    page.on("pageerror", (e) => console.log("PAGE ERROR", key, String(e.message).slice(0, 160)));
    return { key, name, page };
  };
  const host = await open("laptop", "Ana", 1366, 768, "light", false);
  const phone = await open("phone", "Bartholomew X", 390, 844, "dark", true);
  const small = await open("small", "Alexandria Wood", 320, 640, "light", true);
  await host.page.goto(BASE);
  await host.page.locator("#host-name").fill(host.name);
  await host.page.locator("#host-name").press("Enter");
  await host.page.waitForURL(/\/r\/[A-Z]+/);
  const code = /\/r\/([A-Z]+)/.exec(host.page.url())[1];
  for (const p of [phone, small]) {
    await p.page.goto(`${BASE}/r/${code}`);
    await p.page.locator("#join-name").fill(p.name);
    await p.page.getByRole("button", { name: /Join as a contestant/ }).click();
    await p.page.waitForSelector(".contestants");
  }
  const fan = await open("fan", "Fan Club", 390, 844, "dark", true);
  await fan.page.goto(`${BASE}/r/${code}`);
  await fan.page.locator("#join-name").fill(fan.name);
  await fan.page.getByRole("button", { name: /audience/i }).first().click();
  await sleep(1500);
  const tv = await open("tv", "", 1920, 1080, "dark", false);
  await tv.page.goto(`${BASE}/r/${code}?tv=1`);
  const people = [host, phone, small, fan];
  const shot = async (step, who, full = false) => {
    await sleep(700);
    for (const p of who) await p.page.screenshot({ path: path.join(OUT, `${step}-${p.key}.png`), fullPage: full && p.key !== "tv" });
  };
  const tiles = (p) => p.page.locator(".call-strip .call-tile").count();

  // Everyone joins (the TV joins by itself, watch only).
  ok("call button shows when calls are set up", (await host.page.locator(".call-button").count()) === 1);
  for (const p of people) {
    await p.page.locator(".call-button").click();
    await p.page.locator(".call-strip").waitFor({ timeout: 15000 });
  }
  await sleep(3000);
  for (const p of [...people, tv]) ok(`${p.key} sees 4 people in the call`, (await tiles(p)) === 4, `${await tiles(p)} tiles`);
  await shot("joined", [host, phone, small, tv]);

  // Camera on (phone and laptop): frames must arrive elsewhere.
  await phone.page.locator(".call-strip .call-ctl").nth(1).click();
  await host.page.locator(".call-strip .call-ctl").nth(1).click();
  for (let i = 0; i < 30 && (await host.page.evaluate(() => [...document.querySelectorAll(".call-strip video")].filter((v) => v.videoWidth > 0).length)) < 2; i++) await sleep(500);
  for (let i = 0; i < 30 && (await tv.page.evaluate(() => [...document.querySelectorAll(".call-strip video")].filter((v) => v.videoWidth > 0).length)) < 2; i++) await sleep(500);
  const frames = async (p) =>
    p.page.evaluate(() => [...document.querySelectorAll(".call-strip video")].map((v) => v.videoWidth));
  const inspect = async (p) =>
    p.page.evaluate(() => {
      const r = window.__call;
      if (!r) return "no call object";
      return [...r.remoteParticipants.values()].map((x) => `${x.name}: cam=${x.isCameraEnabled} ${[...x.trackPublications.values()].map((t) => `${t.source}/${t.isSubscribed ? "sub" : "unsub"}/${t.track ? "track" : "none"}`).join(",")}`);
    });
  if ((await frames(host)).filter((w) => w > 0).length < 2) {
    console.log("laptop's view:", JSON.stringify(await inspect(host)));
    console.log("phone's own camera on?", await phone.page.evaluate(() => window.__call?.localParticipant.isCameraEnabled));
    console.log("TV's view:", JSON.stringify(await inspect(tv)));
  }
  ok("laptop receives the phone's video", (await frames(host)).filter((w) => w > 0).length >= 2, JSON.stringify(await frames(host)));
  ok("TV receives video", (await frames(tv)).filter((w) => w > 0).length >= 2, JSON.stringify(await frames(tv)));
  // Audio: remote tracks attached and live on players; none on the TV.
  const audio = async (p) =>
    p.page.evaluate(() =>
      [...document.querySelectorAll(".call-strip audio")].filter((a) => a.srcObject && a.srcObject.getAudioTracks().some((t) => t.readyState === "live")).length,
    );
  ok("laptop hears the 3 others", (await audio(host)) === 3, `${await audio(host)} live audio`);
  ok("TV plays no sound", (await tv.page.locator("audio").count()) === 0);
  let speaking = 0;
  for (let i = 0; i < 20 && !speaking; i++) {
    speaking = await host.page.locator(".call-tile.speaking").count();
    if (!speaking) await sleep(300);
  }
  ok("the beep makes someone light up as speaking", speaking > 0, `${speaking} speaking`);
  await shot("video", [host, phone, small, tv]);

  // Mute on the 320 phone: the others see it.
  await small.page.locator(".call-strip .call-ctl").first().click();
  await sleep(2000);
  const mutedSeen = await host.page.locator(".call-strip .call-name", { hasText: "🔇" }).count();
  ok("the laptop sees the 320 phone muted", mutedSeen >= 1, `${mutedSeen} muted names`);

  // The big view, then Escape.
  await phone.page.locator(".call-strip .call-ctl[aria-pressed]").last().click();
  await sleep(1500);
  ok("big view opens", (await phone.page.locator(".call-big").count()) === 1);
  const bigVideos = async () => phone.page.evaluate(() => [...document.querySelectorAll(".call-big video")].filter((v) => v.videoWidth > 0).length);
  for (let i = 0; i < 20 && (await bigVideos()) < 2; i++) await sleep(300);
  ok("big view shows both cameras (yours and the laptop's)", (await bigVideos()) === 2, `${await bigVideos()} playing`);
  await shot("big", [phone]);
  await phone.page.keyboard.press("Escape");
  await sleep(500);
  ok("Escape closes the big view", (await phone.page.locator(".call-big").count()) === 0);

  // A game with the call running: layout and axe.
  const tile = host.page.locator("#classics-h").locator("xpath=ancestor::section[1]").locator("article.seg-ludo");
  await tile.scrollIntoViewIfNeeded();
  await tile.getByRole("button", { name: /^Start!/ }).click();
  await sleep(1500);
  for (const p of [host, phone, small]) await p.page.getByRole("button", { name: /I’m ready/ }).click({ timeout: 4000 }).catch(() => undefined);
  await sleep(2000);
  for (const p of [...people, tv]) {
    const o = await p.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    ok(`${p.key} no sideways overflow in a game`, o === 0, `${o}px`);
  }
  // The top bar clips rather than scrolls, so check every top-bar button is fully on screen.
  for (const p of [...people, tv]) {
    const off = await p.page.evaluate(() =>
      [...document.querySelectorAll(".topbar a, .topbar button")].filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && (r.right > window.innerWidth + 0.5 || r.left < -0.5);
      }).length,
    );
    ok(`${p.key} top bar fits`, off === 0, `${off} buttons off screen`);
  }
  await phone.page.addScriptTag({ path: path.resolve(__dirname, "../../../frontend/node_modules/axe-core/axe.min.js") });
  const axe = await phone.page.evaluate(async () => (await window.axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] })).violations.map((v) => `${v.id}: ${v.nodes[0]?.target}`));
  ok("axe with the call strip", axe.length === 0, JSON.stringify(axe));
  await shot("game", [host, phone, small, tv]);

  // Leaving: the others see one fewer.
  await small.page.locator(".call-strip .call-ctl.leave").click();
  await sleep(3000);
  ok("leaving updates the others", (await tiles(host)) === 3, `${await tiles(host)} tiles`);
  ok("the leaver's strip is gone", (await small.page.locator(".call-strip").count()) === 0);
  await shot("left", [host, small]);
  await b.close();
  console.log(`${results.filter(Boolean).length}/${results.length} checks passed`);
})();

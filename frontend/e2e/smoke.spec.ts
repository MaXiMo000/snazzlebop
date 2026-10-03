import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type BrowserContext, type BrowserContextOptions, type Page } from "@playwright/test";

// One room per viewport, four players in separate contexts (a seat lives in sessionStorage).
// The host's screens are screenshotted at each step for visual QA: e2e/screenshots/<project>/.

const shots = (page: Page, project: string) => async (name: string) =>
  page.screenshot({ path: `e2e/screenshots/${project}/${name}.png`, fullPage: true });

// Extra players' contexts: closed after every test, or their sockets pile up against the server's
// per-IP socket cap (which is right to refuse them).
const opened: BrowserContext[] = [];
async function context(browser: Browser, options: BrowserContextOptions): Promise<BrowserContext> {
  const ctx = await browser.newContext(options);
  opened.push(ctx);
  return ctx;
}
test.afterEach(async () => {
  await Promise.all(opened.splice(0).map((c) => c.close()));
});

function watchConsole(page: Page, problems: string[]) {
  page.on("console", (m) => {
    if (m.type() === "error") problems.push(m.text());
  });
  page.on("pageerror", (e) => problems.push(e.message));
}

async function newPlayer(browser: Browser, baseURL: string, problems: string[]): Promise<Page> {
  const page = await (await context(browser, { baseURL })).newPage();
  watchConsole(page, problems);
  return page;
}

/** axe-core WCAG 2.x A/AA scan; violations are collected and asserted at the end of the test. */
async function axe(page: Page, where: string, found: string[]) {
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  for (const v of violations) found.push(`${where}: ${v.id} (${v.impact}) ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
}

/** Every visible control must be at least 44x44 CSS px (WCAG 2.5.5 / our convention). */
async function targets(page: Page, where: string, found: string[]) {
  const small = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>("button, a[href], input, select, summary, [role=tab], [tabindex='0']")]
      .filter((el) => el.offsetParent !== null && !el.classList.contains("sr-only") && !el.closest(".skip-link"))
      .filter((el) => {
        const r = el.getBoundingClientRect();
        // checkboxes count their whole label (the tap target), not the box alone
        const t = el.matches("input[type=checkbox]") ? el.closest("label")!.getBoundingClientRect() : r;
        return t.width < 44 || t.height < 44;
      })
      .map((el) => `${el.tagName.toLowerCase()} "${(el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 30)}"`),
  );
  for (const s of small) found.push(`${where}: ${s}`);
}

async function skipToResults(host: Page, a11y?: () => Promise<void>) {
  const again = host.getByRole("button", { name: "Play another game" });
  const skip = host.getByRole("button", { name: /Skip wait/ });
  for (let i = 0; i < 30; i++) {
    await expect(skip.or(again).first()).toBeVisible();
    if (await again.isVisible()) break;
    // The Skip button turns into "Play another game" the moment the game ends, so it can vanish
    // between the check above and this click: don't wait for it forever, just look again.
    await skip.click({ timeout: 2000 }).catch(() => undefined);
    await host.waitForTimeout(250);
  }
  await expect(again).toBeVisible();
  await a11y?.();
  await again.click();
  await expect(host.getByRole("heading", { name: "Or play a single game" })).toBeVisible();
}

test("home, create, join, lobby and every game's first screen", async ({ page: host, browser, baseURL }, info) => {
  const problems: string[] = [];
  const a11y: string[] = [];
  watchConsole(host, problems);
  const shot = shots(host, info.project.name);

  // Home
  await host.goto("/");
  await expect(host.getByRole("heading", { level: 1 })).toContainText("Snazzlebop");
  await shot("01-home");
  await axe(host, "home", a11y);
  await targets(host, "home", a11y);

  // Create
  await host.locator("#host-name").fill("Ana");
  await host.getByRole("button", { name: "Create room" }).click();
  await expect(host).toHaveURL(/\/r\/[A-Z]{5}$/);
  const code = host.url().split("/").pop()!;
  // Split-flap board: one tile per letter, plus the code spelled out for screen readers.
  await expect(host.locator(".flap").first()).toContainText(`Room code ${code.split("").join(" ")}`);

  // Join from the home page form
  const bo = await newPlayer(browser, baseURL!, problems);
  await bo.goto("/");
  await bo.locator("#host-name").fill("Bo");
  await bo.getByLabel("Room code").fill(code.toLowerCase());
  await bo.getByRole("button", { name: "Join", exact: true }).click();
  await expect(bo).toHaveURL(new RegExp(`/r/${code}$`));

  // Join from the invite link (join gate)
  const others: Page[] = [];
  for (const name of ["Cy", "Di"]) {
    const p = await newPlayer(browser, baseURL!, problems);
    await p.goto(`/r/${code}`);
    await expect(p.getByRole("heading", { name: `Join room ${code}` })).toBeVisible();
    if (name === "Cy") await p.screenshot({ path: `e2e/screenshots/${info.project.name}/02-join-gate.png`, fullPage: true });
    await p.getByLabel("Your name").fill(name);
    await p.getByRole("button", { name: "Join as a contestant" }).click();
    others.push(p);
  }

  // Lobby
  await expect(host.getByRole("heading", { name: /In the room \(4 online\)/ })).toBeVisible();
  await shot("03-lobby");
  await axe(host, "lobby", a11y);
  await targets(host, "lobby", a11y);

  // Frenemy Radar
  await host.locator("article.game-card.seg-frenemy").getByRole("button", { name: "Start!" }).click();
  await expect(host.getByText(/Rank\s+everyone/)).toBeVisible();
  await expect(bo.getByRole("button", { name: /Lock it in/ })).toBeVisible();
  await shot("04-frenemy");
  await axe(host, "frenemy rank", a11y);
  await targets(host, "frenemy rank", a11y);
  await skipToResults(host, () => axe(host, "frenemy final", a11y));

  // Alibi
  await host.locator("article.game-card.seg-alibi").getByRole("button", { name: "Start!" }).click();
  await expect(host.getByRole("heading", { name: "Read your card!" })).toBeVisible();
  await expect(others[0]!.getByRole("heading", { name: "Your alibi" })).toBeVisible();
  await shot("05-alibi");
  await axe(host, "alibi briefing", a11y);
  await targets(host, "alibi briefing", a11y);
  await skipToResults(host, () => axe(host, "alibi result", a11y));

  // Price Is Weird
  await host.locator("article.game-card.seg-price").getByRole("button", { name: "Start!" }).click();
  await expect(host.getByLabel("Your price ($)")).toBeVisible();
  await expect(others[1]!.getByLabel("Your price ($)")).toBeVisible();
  await shot("06-price");
  await axe(host, "price guess", a11y);
  await targets(host, "price guess", a11y);
  await skipToResults(host, () => axe(host, "price final", a11y));

  // Telepathy Tax
  await host.locator("article.game-card.seg-telepathy").getByRole("button", { name: /Start!/ }).click();
  await expect(host.getByRole("group", { name: /Answers for/ })).toBeVisible();
  await expect(bo.getByRole("group", { name: /Answers for/ }).getByRole("button")).toHaveCount(6);
  await shot("09-telepathy");
  await axe(host, "telepathy pick", a11y);
  await targets(host, "telepathy pick", a11y);
  await skipToResults(host, () => axe(host, "telepathy final", a11y));

  // Mole in the Mural
  await host.locator("article.game-card.seg-mural").getByRole("button", { name: /Start!/ }).click();
  await expect(host.getByRole("group", { name: "The mural, 16 tiles" }).getByRole("button")).toHaveCount(16);
  await expect(host.getByRole("heading", { name: "How it works" })).toBeVisible();
  await shot("10-mural");
  await axe(host, "mural briefing", a11y);
  await targets(host, "mural briefing", a11y);
  await skipToResults(host, () => axe(host, "mural final", a11y));

  // Blackjack Showdown
  await host.locator("article.game-card.seg-blackjack").getByRole("button", { name: /Start!/ }).click();
  await expect(host.getByRole("heading", { name: "Place your bet" })).toBeVisible();
  await expect(bo.getByRole("group", { name: "Bet size" }).getByRole("button")).toHaveCount(4);
  await shot("11-blackjack");
  await axe(host, "blackjack bet", a11y);
  await targets(host, "blackjack bet", a11y);
  await skipToResults(host, () => axe(host, "blackjack final", a11y));

  // Crossword Race
  await host.locator("article.game-card.seg-crossword").getByRole("button", { name: /Start!/ }).click();
  await expect(host.getByLabel(/\d+ (Across|Down) \(\d+ letters\)/)).toBeVisible();
  await expect(host.getByRole("heading", { name: "Across" })).toBeVisible();
  await shot("12-crossword");
  await axe(host, "crossword", a11y);
  await targets(host, "crossword", a11y);
  await skipToResults(host, () => axe(host, "crossword final", a11y));

  expect(problems, "console errors / CSP violations").toEqual([]);
  expect(a11y, "axe WCAG 2.1 A/AA violations").toEqual([]);
});

test("keyboard only: skip link, create a room, start a game, guess", async ({ page, browser, baseURL }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  // Tab forward to the name field, type, submit with Enter.
  const name = page.locator("#host-name");
  for (let i = 0; i < 10 && !(await name.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(name).toBeFocused();
  await page.keyboard.type("Kim");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/r\/[A-Z]{5}$/);
  const code = page.url().split("/").pop()!;

  const guest = await (await context(browser, { baseURL })).newPage();
  await guest.goto(`/r/${code}`);
  await guest.getByLabel("Your name").fill("Lou");
  await guest.getByRole("button", { name: "Join as a contestant" }).click();
  await expect(page.getByRole("heading", { name: /In the room \(2 online\)/ })).toBeVisible();

  // Tab to Price Is Weird's start button and press Enter.
  const start = page.locator("article.game-card.seg-price").getByRole("button", { name: /Start!/ });
  for (let i = 0; i < 40 && !(await start.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(start).toBeFocused();
  // The focus ring must be visible (outline, not removed).
  expect(await start.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
  await page.keyboard.press("Enter");

  const guess = page.getByLabel("Your price ($)");
  await expect(guess).toBeVisible();
  await guess.focus();
  await page.keyboard.type("1234");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: /Locked in/ })).toBeVisible();
});

test("TV mode: read-only big screen of the public state", async ({ page: host, browser, baseURL }, info) => {
  const a11y: string[] = [];
  await host.goto("/");
  await host.locator("#host-name").fill("Host");
  await host.getByRole("button", { name: "Create room" }).click();
  await expect(host).toHaveURL(/\/r\/[A-Z]{5}$/);
  const code = host.url().split("/").pop()!;
  const guest = await (await context(browser, { baseURL })).newPage();
  await guest.goto(`/r/${code}`);
  await guest.getByLabel("Your name").fill("Guest");
  await guest.getByRole("button", { name: "Join as a contestant" }).click();

  const tv = await (await context(browser, { baseURL, viewport: { width: 1600, height: 900 } })).newPage();
  await tv.goto(`/r/${code}?tv=1`);
  await expect(tv.locator(".flap").first()).toContainText(`Room code ${code.split("").join(" ")}`);
  await expect(tv.getByRole("heading", { name: /Contestants \(2 online\)/ })).toBeVisible();
  await axe(tv, "tv lobby", a11y);
  // The TV is not a contestant: the host still sees exactly two players.
  await expect(host.getByRole("heading", { name: /In the room \(2 online\)/ })).toBeVisible();

  await host.locator("article.game-card.seg-price").getByRole("button", { name: /Start!/ }).click();
  await expect(tv.getByText(/0 of 2 guesses locked in/)).toBeVisible();
  await expect(tv.getByLabel("Your price ($)")).toHaveCount(0); // nothing to type into on the TV
  await guest.getByLabel("Your price ($)").fill("100");
  await guest.getByRole("button", { name: "Lock it in!" }).click();
  await expect(tv.getByText(/1 of 2 guesses locked in/)).toBeVisible();
  await expect(tv.getByText("$100")).toHaveCount(0); // a guess is never shown before the reveal
  await tv.screenshot({ path: `e2e/screenshots/${info.project.name}/07-tv.png`, fullPage: true });
  await axe(tv, "tv price", a11y);
  expect(a11y, "axe WCAG 2.1 A/AA violations").toEqual([]);
});

test("reduced motion: the spin lands at once, no stingers or confetti; sound toggle persists", async ({ browser, baseURL }) => {
  const problems: string[] = [];
  const ctx = await context(browser, { baseURL, reducedMotion: "reduce" });
  const host = await ctx.newPage();
  watchConsole(host, problems);
  await host.goto("/");

  // Sound: off by default, toggles, remembered across a reload (it's a per-device preference).
  const sound = host.getByRole("button", { name: "Sound" });
  await expect(sound).toHaveAttribute("aria-pressed", "false");
  await sound.click();
  await expect(sound).toHaveAttribute("aria-pressed", "true");
  await host.reload();
  await expect(host.getByRole("button", { name: "Sound" })).toHaveAttribute("aria-pressed", "true");

  await host.locator("#host-name").fill("Rae");
  await host.getByRole("button", { name: "Create room" }).click();
  await expect(host).toHaveURL(/\/r\/[A-Z]{5}$/);
  const code = host.url().split("/").pop()!;
  const guest = await (await context(browser, { baseURL })).newPage();
  await guest.goto(`/r/${code}`);
  await guest.getByLabel("Your name").fill("Sol");
  await guest.getByRole("button", { name: "Join as a contestant" }).click();
  await host.locator("article.game-card.seg-price").getByRole("button", { name: /Start!/ }).click();
  for (const [p, amount] of [[host, "1"], [guest, "2"]] as const) {
    await p.getByLabel("Your price ($)").fill(amount);
    await p.getByRole("button", { name: "Lock it in!" }).click();
  }
  // No 2.3 s spin: the real price and the results table are there immediately.
  await expect(host.getByRole("region", { name: "Guesses" })).toBeVisible({ timeout: 1500 });
  // The reel's animation is effectively instant, and the price is final (no count-up ticking).
  const spin = await host.locator(".reel").evaluate((el) => parseFloat(getComputedStyle(el).animationDuration));
  expect(spin).toBeLessThan(0.01);
  const shown = await host.locator(".price-tag").textContent();
  await host.waitForTimeout(500);
  await expect(host.locator(".price-tag")).toHaveText(shown!);
  await expect(host.locator(".stinger")).toBeHidden();
  await expect(host.locator(".confetti")).toBeHidden();
  expect(problems).toEqual([]);
});

test("Frenemy result card draws on the device and downloads as a PNG", async ({ page: host, browser, baseURL }, info) => {
  const problems: string[] = [];
  watchConsole(host, problems);
  await host.goto("/");
  await host.locator("#host-name").fill("Ana");
  await host.getByRole("button", { name: "Create room" }).click();
  await expect(host).toHaveURL(/\/r\/[A-Z]{5}$/);
  const code = host.url().split("/").pop()!;
  const players = [host];
  for (const name of ["Bo", "Cy"]) {
    const p = await (await context(browser, { baseURL })).newPage();
    watchConsole(p, problems);
    await p.goto(`/r/${code}`);
    await p.getByLabel("Your name").fill(name);
    await p.getByRole("button", { name: "Join as a contestant" }).click();
    players.push(p);
  }
  await expect(host.getByRole("heading", { name: /In the room \(3 online\)/ })).toBeVisible();
  await host.locator("article.game-card.seg-frenemy").getByRole("button", { name: /Start!/ }).click();
  for (let round = 0; round < 3; round++) {
    for (const p of players) {
      await p.getByRole("button", { name: "The room ranks me number 1" }).click();
      await p.getByRole("button", { name: "Lock it in!" }).click();
    }
    await expect(host.getByText("The room has spoken")).toBeVisible();
    await host.getByRole("button", { name: /Skip wait/ }).click();
  }
  const card = host.getByRole("img", { name: /Result card: Ana, \d+% blind spot/ });
  await expect(card).toBeVisible();
  // The canvas really has pixels on it (not a blank box).
  const inked = await host.locator("canvas.share-canvas").evaluate((c: HTMLCanvasElement) => {
    const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
    let lit = 0;
    for (let i = 0; i < d.length; i += 4 * 97) if (d[i]! > 200) lit++;
    return lit;
  });
  expect(inked).toBeGreaterThan(50);
  const [download] = await Promise.all([host.waitForEvent("download"), host.getByRole("button", { name: "Share my card" }).click()]);
  expect(download.suggestedFilename()).toBe("snazzlebop-frenemy.png");
  await card.screenshot({ path: `e2e/screenshots/${info.project.name}/08-share-card.png` });
  expect(problems, "console errors / CSP violations").toEqual([]);
});

test("host tools: rename the show, lock the room, remove a player", async ({ page: host, browser, baseURL }) => {
  const a11y: string[] = [];
  host.on("dialog", (d) => void d.accept()); // the kick confirmation
  await host.goto("/");
  await host.locator("#host-name").fill("Hal");
  await host.getByRole("button", { name: "Create room" }).click();
  await expect(host).toHaveURL(/\/r\/[A-Z]{5}$/);
  const code = host.url().split("/").pop()!;
  const guest = await (await context(browser, { baseURL })).newPage();
  await guest.goto(`/r/${code}`);
  await guest.getByLabel("Your name").fill("Gil");
  await guest.getByRole("button", { name: "Join as a contestant" }).click();
  await expect(host.getByRole("heading", { name: /In the room \(2 online\)/ })).toBeVisible();

  await host.getByLabel("Show title").fill("Friday Showdown");
  await host.getByRole("button", { name: "Rename" }).click();
  await expect(guest.getByText("Tonight: Friday Showdown")).toBeVisible();

  const lock = host.getByRole("button", { name: /Lock room/ });
  await lock.click();
  await expect(lock).toHaveAttribute("aria-pressed", "true");
  const late = await (await context(browser, { baseURL })).newPage();
  await late.goto(`/r/${code}`);
  await late.getByLabel("Your name").fill("Lou");
  await late.getByRole("button", { name: "Join as a contestant" }).click();
  await expect(late.getByRole("alert")).toHaveText("The host has locked this room");
  await axe(host, "host tools", a11y);

  await host.getByRole("button", { name: "Remove Gil from the room" }).click();
  await expect(guest.getByRole("heading", { name: "You’ve been removed" })).toBeVisible();
  await expect(host.getByRole("heading", { name: /In the room \(1 online\)/ })).toBeVisible();
  expect(a11y).toEqual([]);
});

test("reconnect: a dropped phone shows progress, then comes back on air in the same seat", async ({ page: host, browser, baseURL }) => {
  await host.goto("/");
  await host.locator("#host-name").fill("Max");
  await host.getByRole("button", { name: "Create room" }).click();
  await expect(host).toHaveURL(/\/r\/[A-Z]{5}$/);
  const code = host.url().split("/").pop()!;
  const phone = await (await context(browser, { baseURL })).newPage();
  // Proxy the phone's game socket so the test can cut it and refuse reconnects, like a dead zone.
  let signal = true;
  const live: { close: (o?: { code?: number }) => Promise<void> }[] = [];
  await phone.routeWebSocket(/\/ws\//, (ws) => {
    if (!signal) return void ws.close({ code: 4000 });
    ws.connectToServer();
    live.push(ws);
  });
  await phone.goto(`/r/${code}`);
  await phone.getByLabel("Your name").fill("Nia");
  await phone.getByRole("button", { name: "Join as a contestant" }).click();
  await expect(host.getByRole("heading", { name: /In the room \(2 online\)/ })).toBeVisible();

  signal = false;
  await Promise.all(live.map((ws) => ws.close({ code: 4000 })));
  await expect(phone.getByText(/Signal lost\. Reconnecting/)).toBeVisible();
  await expect(phone.getByRole("button", { name: "Try now" })).toBeVisible();
  await expect(host.getByRole("heading", { name: /In the room \(1 online\)/ })).toBeVisible();

  signal = true;
  await phone.getByRole("button", { name: "Try now" }).click();
  await expect(phone.getByText("Back on air!")).toBeVisible();
  await expect(host.getByRole("heading", { name: /In the room \(2 online\)/ })).toBeVisible();
  await expect(phone.getByText("Nia (you)")).toBeVisible(); // same seat, not a new player
});

/** Host presses Skip until `until` shows up (the next host button after a game ends). */
async function skipUntil(host: Page, until: ReturnType<Page["getByRole"]>) {
  const skip = host.getByRole("button", { name: /Skip wait/ });
  for (let i = 0; i < 150; i++) {  // Liar's Dice can take dozens of skips to play out
    await expect(skip.or(until).first()).toBeVisible();
    if (await until.isVisible()) return;
    await skip.click({ timeout: 2000 }).catch(() => undefined);
    await host.waitForTimeout(250);
  }
  await expect(until).toBeVisible();
}

test("show night: playlist, audience predictions and reactions, jackpot, finale", async ({ page: host, browser, baseURL }, info) => {
  const problems: string[] = [];
  const a11y: string[] = [];
  watchConsole(host, problems);
  const shot = shots(host, info.project.name);
  await host.goto("/");
  await host.locator("#host-name").fill("Ana");
  await host.getByRole("button", { name: "Create room" }).click();
  await expect(host).toHaveURL(/\/r\/[A-Z]{5}$/);
  const code = host.url().split("/").pop()!;
  for (const name of ["Bo", "Cy"]) {
    const p = await newPlayer(browser, baseURL!, problems);
    await p.goto(`/r/${code}`);
    await p.getByLabel("Your name").fill(name);
    await p.getByRole("button", { name: "Join as a contestant" }).click();
    await expect(p.getByText(`${name} (you)`)).toBeVisible();
  }
  const fan = await newPlayer(browser, baseURL!, problems);
  await fan.goto(`/r/${code}`);
  await fan.getByLabel("Your name").fill("Fan");
  await fan.getByRole("button", { name: "Join the audience" }).click();
  await expect(fan.getByText("You’re in the audience")).toBeVisible();
  await axe(fan, "audience lobby", a11y);

  // Plan the show: Price then Telepathy, jackpot on, a show pack.
  await expect(host.getByRole("heading", { name: "Audience" })).toBeVisible();
  await expect(host.getByRole("button", { name: "Remove Fan from the audience" })).toBeVisible();
  await host.getByLabel("Show pack").selectOption("food");
  await expect(fan.getByText("Show pack: Food fight")).toBeVisible();
  const games = host.getByRole("group", { name: "Games in this show, in order" });
  await games.getByRole("button", { name: "Price Is Weird" }).click();
  await games.getByRole("button", { name: "Telepathy Tax" }).click();
  await expect(host.getByRole("button", { name: /Jackpot finale: on/ })).toHaveAttribute("aria-pressed", "true");
  await shot("14-show-builder");
  await axe(host, "show builder", a11y);
  await targets(host, "show builder", a11y);
  await host.getByRole("button", { name: "Start the show (2 games)" }).click();

  // The audience backs a winner and reacts; everyone sees the show strip.
  await expect(host.getByRole("navigation", { name: /Show progress/ })).toBeVisible();
  const predict = fan.getByRole("group", { name: "Predict the winner" });
  await predict.getByRole("button", { name: "Bo" }).click();
  await expect(predict.getByRole("button", { name: "Bo" })).toHaveAttribute("aria-pressed", "true");
  await expect(host.getByText(/Crowd favourite: Bo/)).toBeVisible();
  await fan.getByRole("button", { name: "Applause" }).click();
  await expect(host.locator(".react-overlay .floater")).toHaveCount(1);
  await axe(fan, "audience in game", a11y);
  await targets(fan, "audience in game", a11y);

  await skipUntil(host, host.getByRole("button", { name: /Next: Telepathy Tax/ }));
  await expect(host.getByText("The host says")).toBeVisible();
  await host.getByRole("button", { name: /Next: Telepathy Tax/ }).click();
  await skipUntil(host, host.getByRole("button", { name: /Next: Jackpot finale/ }));
  await host.getByRole("button", { name: /Next: Jackpot finale/ }).click();

  // Jackpot: a secret wager, then the reveal.
  await expect(host.getByRole("heading", { name: "Jackpot Round" })).toBeVisible();
  await host.getByRole("button", { name: "All in" }).click();
  await host.getByRole("button", { name: "Higher" }).click();
  await expect(host.getByText(/Locked: \d+ on higher/)).toBeVisible();
  await expect(fan.getByText(/of 3 wagers locked in/)).toBeVisible(); // the crowd sees counts, not bets
  await shot("15-jackpot");
  await axe(host, "jackpot", a11y);
  await targets(host, "jackpot", a11y);
  await skipUntil(host, host.getByRole("button", { name: /Next: the grand finale/ }));
  await expect(host.getByText("The real price", { exact: true })).toBeVisible();
  await host.getByRole("button", { name: /Next: the grand finale/ }).click();

  // The finale, on the host's phone and the audience's.
  await expect(host.getByRole("heading", { name: "Final standings" })).toBeVisible();
  await expect(host.getByRole("heading", { name: "Awards" })).toBeVisible();
  await expect(fan.getByRole("heading", { name: "Final standings" })).toBeVisible();
  await shot("16-finale");
  await expect(host.locator(".confetti")).toHaveCount(0, { timeout: 6000 }); // decorative, ~3.6 s
  await axe(host, "finale", a11y);
  await targets(host, "finale", a11y);
  await host.getByRole("button", { name: "Back to the lobby" }).click();
  await expect(host.getByRole("heading", { name: "Plan a show night" })).toBeVisible();
  expect(a11y).toEqual([]);
  expect(problems).toEqual([]);
});

async function table(browser: Browser, baseURL: string, host: Page, names: string[], problems: string[]) {
  await host.goto("/");
  await host.locator("#host-name").fill("Ana");
  await host.getByRole("button", { name: "Create room" }).click();
  await expect(host).toHaveURL(/\/r\/[A-Z]{5}$/);
  const code = host.url().split("/").pop()!;
  const guests: Page[] = [];
  for (const name of names) {
    const p = await newPlayer(browser, baseURL, problems);
    await p.goto(`/r/${code}`);
    await p.getByLabel("Your name").fill(name);
    await p.getByRole("button", { name: "Join as a contestant" }).click();
    await expect(p.getByText(`${name} (you)`)).toBeVisible();
    guests.push(p);
  }
  return guests;
}

test("the newer games: first screens, a real move each, axe and targets", async ({ page: host, browser, baseURL }, info) => {
  test.setTimeout(8 * 60_000); // eight games, three phones
  const problems: string[] = [];
  const a11y: string[] = [];
  watchConsole(host, problems);
  const shot = shots(host, info.project.name);
  const [bo, cy] = await table(browser, baseURL!, host, ["Bo", "Cy"], problems);
  const start = async (id: string) => {
    await host.locator(`article.game-card.seg-${id}`).getByRole("button", { name: /Start!/ }).click();
  };
  const back = async () => {
    await skipUntil(host, host.getByRole("button", { name: "Play another game" }));
    await host.getByRole("button", { name: "Play another game" }).click();
    await expect(host.getByRole("heading", { name: "Or play a single game" })).toBeVisible();
  };
  const check = async (name: string) => {
    await shot(name);
    await axe(host, name, a11y);
    await targets(host, name, a11y);
  };

  // Liar's Dice: whoever's turn it is opens the bidding.
  await start("dice");
  await expect(host.getByRole("heading", { name: "Liar's Dice" })).toBeVisible();
  await check("17-dice");
  const bidder = [host, bo, cy];
  for (const p of bidder) {
    const bid = p.getByRole("button", { name: /^Bid / });
    if (await bid.isVisible()) {
      await bid.click();
      break;
    }
  }
  await expect(host.getByText(/says there are at least/)).toBeVisible();
  await back();

  // Split or Steal
  await start("split");
  await expect(host.getByRole("heading", { name: "Split or Steal" })).toBeVisible();
  await check("18-split");
  await back();

  // Chicken Run: get through the countdown and cash out.
  await start("chicken");
  await expect(host.getByRole("heading", { name: "Dirty tricks" })).toBeVisible();
  await host.getByRole("button", { name: /Insure/ }).click();
  await expect(host.getByRole("button", { name: /Insured/ })).toBeDisabled();
  await expect(host.getByRole("button", { name: "Cash out!" })).toBeVisible({ timeout: 15_000 });
  await check("19-chicken");
  await host.getByRole("button", { name: "Cash out!" }).click();
  await expect(host.getByText(/You banked \d+/)).toBeVisible();
  await back();

  // Wager Wits: answer, then the board.
  await start("wits");
  for (const [p, v] of [[host, "10"], [bo, "200"], [cy, "3000"]] as const) {
    await p.getByLabel(/Your answer/).fill(v);
    await p.getByRole("button", { name: "Lock it in!" }).click();
  }
  await expect(host.getByRole("group", { name: "Answer slots" })).toBeVisible();
  await check("20-wits");
  await back();

  // Code Crackers: everyone hides a code, then the host makes a guess.
  await start("codes");
  for (const p of [host, bo, cy]) {
    for (let i = 0; i < 4; i++) await p.getByRole("button", { name: "banana" }).click();
    await p.getByRole("button", { name: "Lock my code" }).click();
  }
  await expect(host.getByText(/Cracking /)).toBeVisible();
  for (let i = 0; i < 4; i++) await host.getByRole("button", { name: "banana" }).click();
  await host.getByRole("button", { name: "Guess" }).click();
  await expect(host.getByText("Cracked by Ana", { exact: false }).or(host.getByLabel(/4 right place/))).toBeVisible();
  await check("21-codes");
  await back();

  // Roulette Royale: whoever isn't the House places a bet.
  await start("roulette");
  await expect(host.getByRole("heading", { name: "Roulette Royale" })).toBeVisible();
  await check("22-roulette");
  for (const p of [host, bo, cy]) {
    const red = p.getByRole("button", { name: "Red", exact: true });
    if (await red.isVisible()) {
      await red.click();
      await p.getByRole("button", { name: /Lock in/ }).click();
    } else {
      await p.getByRole("button", { name: "Lock in", exact: true }).click(); // the House keeps its cover
    }
  }
  await expect(host.getByText("The wheel says")).toBeVisible();
  await back();

  // Lowest Lonely Number: everyone picks; the lowest unique number wins.
  await start("lonely");
  await expect(host.getByRole("heading", { name: "Lowest Lonely Number" })).toBeVisible();
  await check("24-lonely");
  for (const [p, n] of [[host, "2"], [bo, "2"], [cy, "5"]] as const) {
    await p.getByRole("group", { name: "Pick a number" }).getByRole("button", { name: n, exact: true }).click();
  }
  await expect(host.getByText(/wins 100 with/)).toBeVisible();
  await expect(host.getByText("Cy", { exact: false }).first()).toBeVisible();
  await back();

  // Mystery Box Auction: everyone sees their own peek; a bid takes the top spot.
  await start("boxes");
  await expect(host.getByText("Only you know")).toBeVisible();
  await check("25-boxes");
  await skipUntil(host, host.getByRole("button", { name: "Bid 10", exact: true }));
  await host.getByRole("button", { name: "Bid 10", exact: true }).click();
  await expect(bo.getByText(/Top bid 10 by Ana/)).toBeVisible();
  await bo.getByRole("button", { name: "Bid 60", exact: true }).click();
  await expect(host.getByText(/Top bid 60 by Bo/)).toBeVisible();
  await check("25-boxes-bidding");
  await back();

  expect(a11y).toEqual([]);
  expect(problems).toEqual([]);
});

test("show extras: power cards, rivals, MVP votes, rematch and the season", async ({ page: host, browser, baseURL }, info) => {
  test.setTimeout(5 * 60_000);
  const problems: string[] = [];
  const a11y: string[] = [];
  watchConsole(host, problems);
  const shot = shots(host, info.project.name);
  const [bo, cy] = await table(browser, baseURL!, host, ["Bo", "Cy"], problems);
  const games = host.getByRole("group", { name: "Games in this show, in order" });
  await games.getByRole("button", { name: "Lowest Lonely Number" }).click();
  await games.getByRole("button", { name: "Split or Steal" }).click();
  await host.getByRole("button", { name: /Jackpot finale: on/ }).click();
  await host.getByRole("button", { name: "Start the show (2 games)" }).click();

  await expect(host.getByRole("heading", { name: "Lowest Lonely Number" })).toBeVisible();
  await expect(host.getByRole("heading", { name: /Power cards/ })).toBeVisible();
  await expect(host.getByRole("heading", { name: /Rivals/ })).toBeVisible();
  await expect(host.getByText(/Your rival this game:|sits out/).or(host.getByRole("heading", { name: /Rivals/ })).first()).toBeVisible();
  // The host picks first, so a Peek always has something to see.
  await host.getByRole("group", { name: "Pick a number" }).getByRole("button", { name: "3", exact: true }).click();
  await bo.getByRole("button", { name: /^Play / }).click();
  await expect(bo.getByText(/You played/)).toBeVisible();
  await expect(host.getByText(/1 in play this game/)).toBeVisible();
  await shot("26-cards");
  await axe(bo, "power card", a11y);
  await targets(bo, "power card", a11y);
  for (const [p, n] of [[bo, "5"], [cy, "7"]] as const) {
    await p.getByRole("group", { name: "Pick a number" }).getByRole("button", { name: n, exact: true }).click();
  }
  await skipUntil(host, host.getByRole("button", { name: /Next: Split or Steal/ }));
  await expect(host.getByRole("heading", { name: /Cards on the table/ })).toBeVisible();
  await expect(host.getByText(/Bo played/)).toBeVisible();
  await host.getByRole("button", { name: /Next: Split or Steal/ }).click();
  await skipUntil(host, host.getByRole("button", { name: /Next: the grand finale/ }));
  await host.getByRole("button", { name: /Next: the grand finale/ }).click();
  await expect(host.getByRole("heading", { name: /The season: 1 show/ })).toBeVisible();
  await expect(host.locator(".confetti")).toHaveCount(0, { timeout: 6000 });
  await axe(host, "season finale", a11y);
  await host.getByRole("button", { name: /Rematch/ }).click();
  await expect(host.getByRole("heading", { name: "Lowest Lonely Number" })).toBeVisible();
  await expect(cy.getByRole("heading", { name: "Lowest Lonely Number" })).toBeVisible();
  expect(a11y).toEqual([]);
  expect(problems).toEqual([]);
});

test("Friend Stock Exchange: trade before each game, prices move, books revealed at the finale", async ({ page: host, browser, baseURL }, info) => {
  const problems: string[] = [];
  const a11y: string[] = [];
  watchConsole(host, problems);
  const shot = shots(host, info.project.name);
  const [bo] = await table(browser, baseURL!, host, ["Bo", "Cy"], problems);
  const games = host.getByRole("group", { name: "Games in this show, in order" });
  await games.getByRole("button", { name: "Price Is Weird" }).click();
  await games.getByRole("button", { name: "Telepathy Tax" }).click();
  await host.getByRole("button", { name: /Jackpot finale: on/ }).click();
  await host.getByRole("button", { name: /Friend Stock Exchange: off/ }).click();
  await host.getByRole("button", { name: "Start the show (2 games)" }).click();

  await expect(host.getByRole("heading", { name: "Friend Stock Exchange" })).toBeVisible();
  await bo.getByRole("button", { name: "Buy 5 shares of Ana" }).click();
  await expect(bo.getByText("5 held")).toBeVisible();
  await expect(bo.getByText(/Cash \$500/)).toBeVisible();
  await expect(host.getByText(/1 trades so far/)).toBeVisible();
  await shot("23-market");
  await axe(host, "market", a11y);
  await targets(host, "market", a11y);
  await host.getByRole("button", { name: /Ring the bell now/ }).click();
  await expect(host.getByRole("heading", { name: "Price Is Weird" })).toBeVisible();

  await skipUntil(host, host.getByRole("button", { name: /Next: Telepathy Tax/ }));
  await expect(host.getByRole("heading", { name: /The market reacts/ })).toBeVisible();
  await host.getByRole("button", { name: /Next: Telepathy Tax/ }).click();
  await expect(host.getByRole("heading", { name: "Friend Stock Exchange" })).toBeVisible();
  await host.getByRole("button", { name: /Ring the bell now/ }).click();
  await skipUntil(host, host.getByRole("button", { name: /Next: the grand finale/ }));
  await host.getByRole("button", { name: /Next: the grand finale/ }).click();
  await expect(host.getByRole("heading", { name: /closing bell/ })).toBeVisible();
  await expect(host.getByText(/held 5 × Ana/)).toBeVisible(); // Bo's book, public at last
  await expect(host.locator(".confetti")).toHaveCount(0, { timeout: 6000 }); // decorative, ~3.6 s
  await axe(host, "market finale", a11y);
  expect(a11y).toEqual([]);
  expect(problems).toEqual([]);
});

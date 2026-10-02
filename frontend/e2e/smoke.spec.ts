import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

// One room per viewport, four players in separate contexts (a seat lives in sessionStorage).
// The host's screens are screenshotted at each step for visual QA: e2e/screenshots/<project>/.

const shots = (page: Page, project: string) => async (name: string) =>
  page.screenshot({ path: `e2e/screenshots/${project}/${name}.png`, fullPage: true });

function watchConsole(page: Page, problems: string[]) {
  page.on("console", (m) => {
    if (m.type() === "error") problems.push(m.text());
  });
  page.on("pageerror", (e) => problems.push(e.message));
}

async function newPlayer(browser: Browser, baseURL: string, problems: string[]): Promise<Page> {
  const page = await (await browser.newContext({ baseURL })).newPage();
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
  await expect(host.getByRole("heading", { name: "Pick a game" })).toBeVisible();
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
    await p.getByRole("button", { name: "Join", exact: true }).click();
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
  await expect(bo.getByRole("button", { name: "Lock it in!" })).toBeVisible();
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

  const guest = await (await browser.newContext({ baseURL })).newPage();
  await guest.goto(`/r/${code}`);
  await guest.getByLabel("Your name").fill("Lou");
  await guest.getByRole("button", { name: "Join", exact: true }).click();
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
  const guest = await (await browser.newContext({ baseURL })).newPage();
  await guest.goto(`/r/${code}`);
  await guest.getByLabel("Your name").fill("Guest");
  await guest.getByRole("button", { name: "Join", exact: true }).click();

  const tv = await (await browser.newContext({ baseURL, viewport: { width: 1600, height: 900 } })).newPage();
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
  const ctx = await browser.newContext({ baseURL, reducedMotion: "reduce" });
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
  const guest = await (await browser.newContext({ baseURL })).newPage();
  await guest.goto(`/r/${code}`);
  await guest.getByLabel("Your name").fill("Sol");
  await guest.getByRole("button", { name: "Join", exact: true }).click();
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
    const p = await (await browser.newContext({ baseURL })).newPage();
    watchConsole(p, problems);
    await p.goto(`/r/${code}`);
    await p.getByLabel("Your name").fill(name);
    await p.getByRole("button", { name: "Join", exact: true }).click();
    players.push(p);
  }
  await expect(host.getByRole("heading", { name: /In the room \(3 online\)/ })).toBeVisible();
  await host.locator("article.game-card.seg-frenemy").getByRole("button", { name: /Start!/ }).click();
  for (let round = 0; round < 3; round++) {
    for (const p of players) await p.getByRole("button", { name: "Lock it in!" }).click();
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
  const guest = await (await browser.newContext({ baseURL })).newPage();
  await guest.goto(`/r/${code}`);
  await guest.getByLabel("Your name").fill("Gil");
  await guest.getByRole("button", { name: "Join", exact: true }).click();
  await expect(host.getByRole("heading", { name: /In the room \(2 online\)/ })).toBeVisible();

  await host.getByLabel("Show title").fill("Friday Showdown");
  await host.getByRole("button", { name: "Rename" }).click();
  await expect(guest.getByText("Tonight: Friday Showdown")).toBeVisible();

  const lock = host.getByRole("button", { name: /Lock room/ });
  await lock.click();
  await expect(lock).toHaveAttribute("aria-pressed", "true");
  const late = await (await browser.newContext({ baseURL })).newPage();
  await late.goto(`/r/${code}`);
  await late.getByLabel("Your name").fill("Lou");
  await late.getByRole("button", { name: "Join", exact: true }).click();
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
  const phone = await (await browser.newContext({ baseURL })).newPage();
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
  await phone.getByRole("button", { name: "Join", exact: true }).click();
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

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

async function skipToResults(host: Page, a11y?: () => Promise<void>) {
  const again = host.getByRole("button", { name: "Play another game" });
  for (let i = 0; i < 20 && !(await again.isVisible()); i++) {
    await host.getByRole("button", { name: /Skip wait/ }).click();
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

  // Frenemy Radar
  await host.locator("article.game-card.frenemy").getByRole("button", { name: "Start!" }).click();
  await expect(host.getByText(/Rank\s+everyone/)).toBeVisible();
  await expect(bo.getByRole("button", { name: "Lock it in!" })).toBeVisible();
  await shot("04-frenemy");
  await axe(host, "frenemy rank", a11y);
  await skipToResults(host, () => axe(host, "frenemy final", a11y));

  // Alibi
  await host.locator("article.game-card.alibi").getByRole("button", { name: "Start!" }).click();
  await expect(host.getByRole("heading", { name: "Read your card!" })).toBeVisible();
  await expect(others[0]!.getByRole("heading", { name: "Your alibi" })).toBeVisible();
  await shot("05-alibi");
  await axe(host, "alibi briefing", a11y);
  await skipToResults(host, () => axe(host, "alibi result", a11y));

  // Price Is Weird
  await host.locator("article.game-card.price").getByRole("button", { name: "Start!" }).click();
  await expect(host.getByLabel("Your price ($)")).toBeVisible();
  await expect(others[1]!.getByLabel("Your price ($)")).toBeVisible();
  await shot("06-price");
  await axe(host, "price guess", a11y);
  await skipToResults(host, () => axe(host, "price final", a11y));

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
  const start = page.locator("article.game-card.price").getByRole("button", { name: /Start!/ });
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

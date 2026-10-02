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

async function skipToResults(host: Page) {
  const again = host.getByRole("button", { name: "Play another game" });
  for (let i = 0; i < 20 && !(await again.isVisible()); i++) {
    await host.getByRole("button", { name: /Skip wait/ }).click();
    await host.waitForTimeout(250);
  }
  await expect(again).toBeVisible();
  await again.click();
  await expect(host.getByRole("heading", { name: "Pick a game" })).toBeVisible();
}

test("home, create, join, lobby and every game's first screen", async ({ page: host, browser, baseURL }, info) => {
  const problems: string[] = [];
  watchConsole(host, problems);
  const shot = shots(host, info.project.name);

  // Home
  await host.goto("/");
  await expect(host.getByRole("heading", { level: 1 })).toContainText("Snazzlebop");
  await shot("01-home");

  // Create
  await host.locator("#host-name").fill("Ana");
  await host.getByRole("button", { name: "Create room" }).click();
  await expect(host).toHaveURL(/\/r\/[A-Z]{5}$/);
  const code = host.url().split("/").pop()!;
  await expect(host.getByText(code, { exact: true })).toBeVisible();

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

  // Frenemy Radar
  await host.locator("article.game-card.frenemy").getByRole("button", { name: "Start!" }).click();
  await expect(host.getByText(/Rank\s+everyone/)).toBeVisible();
  await expect(bo.getByRole("button", { name: "Lock it in!" })).toBeVisible();
  await shot("04-frenemy");
  await skipToResults(host);

  // Alibi
  await host.locator("article.game-card.alibi").getByRole("button", { name: "Start!" }).click();
  await expect(host.getByRole("heading", { name: "Read your card!" })).toBeVisible();
  await expect(others[0]!.getByRole("heading", { name: "Your alibi" })).toBeVisible();
  await shot("05-alibi");
  await skipToResults(host);

  // Price Is Weird
  await host.locator("article.game-card.price").getByRole("button", { name: "Start!" }).click();
  await expect(host.getByLabel("Your price ($)")).toBeVisible();
  await expect(others[1]!.getByLabel("Your price ($)")).toBeVisible();
  await shot("06-price");
  await skipToResults(host);

  expect(problems, "console errors / CSP violations").toEqual([]);
});

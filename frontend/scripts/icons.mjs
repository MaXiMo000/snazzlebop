// Rasterise the SVG icons to the PNG sizes the web manifest and iOS need.
//   node scripts/icons.mjs     (uses Playwright's Chromium; outputs into public/)
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";

const jobs = [
  ["public/favicon.svg", "public/icon-192.png", 192],
  ["public/favicon.svg", "public/icon-512.png", 512],
  ["public/icon-maskable.svg", "public/icon-maskable-512.png", 512],
  ["public/icon-maskable.svg", "public/apple-touch-icon.png", 180],
];
const browser = await chromium.launch();
const page = await browser.newPage();
for (const [src, out, size] of jobs) {
  await page.setViewportSize({ width: size, height: size });
  const svg = readFileSync(src, "utf8").replace("<svg ", `<svg width="${size}" height="${size}" `);
  await page.setContent(`<body style="margin:0;background:transparent">${svg}</body>`);
  await page.locator("svg").screenshot({ path: out, omitBackground: true });
  console.log(out);
}
await browser.close();

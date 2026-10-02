// Reads Lighthouse JSON reports and fails unless accessibility, best practices and SEO are >= 95.
// Prints every audit that cost points in those categories so it can be fixed, not guessed at.
import { readdirSync, readFileSync } from "node:fs";

const dir = process.argv[2] ?? "lighthouse";
const GATED = ["accessibility", "best-practices", "seo"];
// Room pages are private and short-lived: robots.txt disallows /r/ on purpose, so "is-crawlable" is
// the one audit we expect to fail there. Everything else is gated as normal.
const EXPECTED = { "join-gate": ["is-crawlable"] };
let failed = false;
for (const file of readdirSync(dir).filter((f) => f.endsWith(".json")).sort()) {
  const report = JSON.parse(readFileSync(`${dir}/${file}`, "utf8"));
  const cats = Object.values(report.categories);
  console.log(`${file.replace(".json", "").padEnd(18)} ${cats.map((c) => `${c.id}=${Math.round(c.score * 100)}`).join("  ")}`);
  const allowed = EXPECTED[file.replace(/-(mobile|desktop)\.json$/, "")] ?? [];
  for (const cat of cats.filter((c) => GATED.includes(c.id))) {
    // Recompute the category score without the expected audits.
    let got = 0;
    let total = 0;
    for (const ref of cat.auditRefs) {
      const a = report.audits[ref.id];
      if (ref.weight === 0 || a.score === null) continue;
      if (a.score < 1) console.log(`   - [${cat.id}] ${a.id}: ${a.title}${allowed.includes(a.id) ? " (expected, not counted)" : ""}`);
      if (allowed.includes(a.id)) continue;
      got += a.score * ref.weight;
      total += ref.weight;
    }
    if (total && got / total < 0.95) failed = true;
  }
}
process.exit(failed ? 1 : 0);

// Headless screenshots of every dashboard view into docs/img (served by the running API at :18000).
// Usage: node scripts/screenshots.mjs [baseUrl]
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const base = process.argv[2] ?? "http://127.0.0.1:18000";
const out = new URL("../../docs/img/", import.meta.url).pathname;
mkdirSync(out, { recursive: true });

const hero = "session=demo-soccer-hero";
const shots = [
  ["live-hero", `?${hero}&view=live&t=1832000&paused&overlays=trails,hulls,defline,labels`, 5000],
  ["live-voronoi", `?${hero}&view=live&t=3421000&paused&overlays=voronoi,trails,labels`, 5000],
  ["live-heatmap", `?${hero}&view=live&t=5000000&paused&overlays=heatmap,labels&pick=skillcorner:player:23418`, 6000],
  ["live-similar", `?${hero}&view=live&t=2410000&paused&similar&overlays=hulls,trails,labels`, 7000],
  ["live-analyst", `?${hero}&view=live&t=4200000&paused&overlays=hulls,defline,labels&ask=${encodeURIComponent("Which players covered the most distance?")}`, 8000, ".answer-foot"],
  ["players", `?${hero}&view=players`, 9000],
  ["pipeline-faults", `?session=demo-soccer-faults&view=pipeline`, 12000],
  ["catalog", `?${hero}&view=catalog`, 4000],
  ["live-nba", `?session=demo-nba&view=live&t=1210000&paused&overlays=trails,hulls,labels`, 6000],
];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
const errors = [];
page.on("pageerror", e => errors.push(String(e)));
page.on("console", m => m.type() === "error" && errors.push(m.text()));
for (const [name, q, wait, scrollTo] of shots) {
  await page.goto(base + "/" + q, { waitUntil: "load" });
  await page.waitForTimeout(wait);
  if (scrollTo) {
    await page.locator(scrollTo).first().evaluate(el => el.scrollIntoView({ block: "end" }));
    await page.waitForTimeout(500);
  }
  await page.screenshot({ path: `${out}${name}.png`, fullPage: false });
  console.log("saved", name);
}
await browser.close();
if (errors.length) { console.error("page errors:\n" + errors.join("\n")); process.exit(1); }

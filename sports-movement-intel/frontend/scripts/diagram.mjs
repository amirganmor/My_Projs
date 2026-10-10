// Renders docs/diagrams/architecture.html to docs/img/architecture.png.
// Usage: node scripts/diagram.mjs
import { chromium } from "playwright";

const src = new URL("../../docs/diagrams/architecture.html", import.meta.url);
const out = new URL("../../docs/img/architecture.png", import.meta.url).pathname;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1900, height: 1200 }, deviceScaleFactor: 2 });
await page.goto(src.href, { waitUntil: "load" });
await page.waitForFunction(() => window.__ready === true);
await page.locator("#canvas").screenshot({ path: out });
await browser.close();
console.log("saved", out);

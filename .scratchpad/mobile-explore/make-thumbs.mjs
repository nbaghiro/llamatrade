// Screenshots the recommended option of each area's first surface, in light and dark, for index.html.
// Run after build-viewer.py: node make-thumbs.mjs
import { chromium } from "/Users/naib/.npm/_npx/9833c18b2d85bc59/node_modules/playwright-core/index.mjs";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname);
const areas = ["onboarding", "checkin", "alerts", "glance", "markets-mobile", "copilot-mobile", "edge"];
fs.mkdirSync(path.join(here, "thumbs"), { recursive: true });
const browser = await chromium.launch({ channel: "chrome" });
for (const mode of ["light", "dark"]) {
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 }, deviceScaleFactor: 1 });
  await ctx.addInitScript((m) => { try { localStorage.setItem("ax-mode", m); } catch (e) { /* storage blocked */ } }, mode);
  const page = await ctx.newPage();
  for (const a of areas) {
    const file = path.join(here, `area-${a}.html`);
    if (!fs.existsSync(file)) continue;
    await page.goto("file://" + file);
    await page.waitForTimeout(600);
    await page.evaluate(() => {
      const sec = document.querySelector(".ax-surface");
      const rec = [...sec.querySelectorAll(".ax-tab")].find((t) => t.classList.contains("rec")) || sec.querySelector(".ax-tab");
      rec.click();
      document.querySelectorAll(".ax-cap, .ax-zbtn, .ax-dock").forEach((e) => (e.style.visibility = "hidden"));
      sec.scrollIntoView();
    });
    await page.waitForTimeout(250);
    const el = await page.$(".ax-surface .ax-opt.on .ax-phones");
    await el.screenshot({ path: path.join(here, "thumbs", `${a}-${mode}.png`) });
  }
  await ctx.close();
}
await browser.close();
console.log("thumbs written");

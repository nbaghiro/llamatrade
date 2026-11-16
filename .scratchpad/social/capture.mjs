// Photographs LlamaTrade into m/, light and in a dark preview, for the ad studio.
//
//   node capture.mjs                 every surface, both themes
//   ONLY=builder,portfolio node ...  some of them
//   THEMES=light node ...            one theme
//
// Read-only: it signs in as the seeded demo account and never submits a form beyond that.
// The dark pass injects a theme over the product rather than changing it. Monolith already
// carries a [data-theme] hook and semantic aliases, so the surfaces are a few lines; the
// shadows are not, because the hard offset shadow is built from the same ink as the text,
// and at full strength it becomes a light slab on a dark ground. The preview dials those to
// a translucent edge, which is the open design question made visible rather than hidden.
const PW = process.env.HOME + "/Documents/code/galleo/node_modules/playwright/index.mjs";
const { chromium } = await import(PW);
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const HERE = import.meta.dirname;
const OUT = join(HERE, "m");
const APP = "http://localhost:8800";
const ONLY = (process.env.ONLY ?? "").split(",").filter(Boolean);
const THEMES = (process.env.THEMES ?? "light,dark").split(",").filter(Boolean);
mkdirSync(OUT, { recursive: true });

const DARK = `
  html:root, html[data-theme='monolith'] {
    --lt-bone: 20 20 23;
    --lt-paper: 30 30 34;
    --lt-ink: 239 236 229;
    --lt-line: rgb(var(--lt-ink) / 0.16);
    --lt-grid-dot: rgb(var(--lt-ink) / 0.08);
    --lt-shadow-sm: 2px 2px 0 rgb(var(--lt-ink) / 0.22);
    --lt-shadow: 4px 4px 0 rgb(var(--lt-ink) / 0.20);
    --lt-shadow-lg: 8px 8px 0 rgb(var(--lt-ink) / 0.18);
    --lt-shadow-xl: 12px 12px 0 rgb(var(--lt-ink) / 0.16);
  }
  html, body { background: rgb(var(--lt-bone)); color-scheme: dark; }
`;

const SURFACES = [
    // the public pages are shot signed out, or the app redirects them to /home
    { name: "marketing", path: "/", auth: false, settle: 3000 },
    { name: "login", path: "/login", auth: false, settle: 1800 },
    { name: "dashboard", path: "/dashboard", auth: true, settle: 4500 },
    { name: "strategies", path: "/strategies", auth: true, settle: 3500 },
    { name: "backtest", path: "/backtest", auth: true, settle: 4500 },
    { name: "portfolio", path: "/portfolio", auth: true, settle: 4000 },
    { name: "copilot", path: "/copilot", auth: true, settle: 3500 },
    { name: "wallet", path: "/wallet", auth: true, settle: 3500 },
];

const want = (n) => !ONLY.length || ONLY.includes(n);

const b = await chromium.launch({ channel: "chrome" });
for (const theme of THEMES) {
    const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    const errs = [];
    page.on("pageerror", (e) => errs.push(String(e).slice(0, 80)));

    // the signed-out pages first, while this context has no session
    for (const s2 of SURFACES.filter((x) => !x.auth && want(x.name))) {
        await page.goto(`${APP}${s2.path}`, { waitUntil: "domcontentloaded" });
        await page.waitForTimeout(s2.settle);
        if (theme === "dark") await page.addStyleTag({ content: DARK });
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(400);
        await page.screenshot({ path: join(OUT, `lt-${s2.name}-${theme}.png`) });
        process.stdout.write(`  lt-${s2.name}-${theme}\n`);
    }

    // then sign in once, and the rest reuse the session
    await page.goto(`${APP}/login`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);
    if (await page.locator('input[type="email"]').count()) {
        await page.fill('input[type="email"]', "demo@llamatrade.ai");
        if (await page.locator('input[type="password"]').count())
            await page.fill('input[type="password"]', "demo1234");
        await page.getByRole("button", { name: /sign in|log in|continue/i }).first().click();
        await page.waitForTimeout(6000);
    }
    const authed = !/\/login/.test(page.url());
    process.stdout.write(`${theme}: signed in = ${authed}\n`);

    for (const s2 of SURFACES.filter((x) => x.auth && want(x.name))) {
        if (!authed) break;
        await page.goto(`${APP}${s2.path}`, { waitUntil: "domcontentloaded" });
        await page.waitForTimeout(s2.settle);
        if (theme === "dark") await page.addStyleTag({ content: DARK });
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(400);
        await page.screenshot({ path: join(OUT, `lt-${s2.name}-${theme}.png`) });
        process.stdout.write(`  lt-${s2.name}-${theme}\n`);
    }
    if (errs.length) process.stdout.write(`  page errors: ${errs.slice(0, 2).join(" | ")}\n`);
    await ctx.close();
}
await b.close();

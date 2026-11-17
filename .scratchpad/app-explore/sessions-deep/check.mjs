// Render-check: node check.mjs <page.html relative to app-explore> [surfaceIdSubstring]
// Opens in light and dark, visits every option, reports console errors, undrawn charts and clipped content.
import { chromium } from "/Users/naib/.npm/_npx/9833c18b2d85bc59/node_modules/playwright-core/index.mjs";
import path from "node:path";
const page_ = process.argv[2] || "area-sessions-2.html";
const only = process.argv[3] || "";
const shots = process.argv[4] || "";
const url = "file://" + path.resolve("/Users/naib/Documents/code/llamatrade/.scratchpad/app-explore", page_);
const browser = await chromium.launch({ channel: "chrome" });
for (const mode of ["light", "dark"]) {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  await ctx.addInitScript((m) => { try { localStorage.setItem("ax-mode", m); localStorage.removeItem("ax-picks"); } catch (e) {} }, mode);
  const pg = await ctx.newPage();
  const errs = [];
  pg.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errs.push(m.type() + ": " + m.text()); });
  pg.on("pageerror", (e) => errs.push("pageerror: " + e.message));
  await pg.goto(url);
  await pg.waitForTimeout(800);
  const secs = await pg.$$eval("section.ax-surface", (s) => s.map((x) => ({ id: x.id, opts: [...x.querySelectorAll(".ax-tab")].map((b) => b.dataset.opt) })));
  for (const s of secs) {
    if (only && !s.id.includes(only)) continue;
    for (const o of s.opts) {
      await pg.click(`#${s.id} .ax-tab[data-opt="${o}"]`);
      await pg.waitForTimeout(120);
      const res = await pg.evaluate(({ id, o }) => {
        const opt = document.querySelector(`#${id} .ax-opt[data-opt="${o}"]`);
        const out = [];
        opt.querySelectorAll("[data-chart]").forEach((c) => { if (!c.dataset.axDone) out.push("undrawn chart " + c.dataset.chart); });
        opt.querySelectorAll(".ax-frame").forEach((f, fi) => {
          const kind = f.dataset.frame;
          const dev = f.querySelector(".ax-dev");
          const scr = dev.querySelector(".ax-win-scr, .ax-phone-scr");
          const sr = scr.getBoundingClientRect();
          const sc = sr.width / scr.offsetWidth;
          // anything visible extending past the screen (right or bottom)
          let worst = null;
          scr.querySelectorAll("*").forEach((el) => {
            if (el.closest(".art, .glow, svg")) return;
            const st = getComputedStyle(el);
            if (st.display === "none" || st.visibility === "hidden" || st.position === "fixed") return;
            const r = el.getBoundingClientRect();
            if (!r.width || !r.height) return;
            const dr = (r.right - sr.right) / sc, db = (r.bottom - sr.bottom) / sc, dl = (sr.left - r.left) / sc;
            const d = Math.max(dr, db, dl);
            if (d > 2 && (!worst || d > worst.d)) worst = { d: Math.round(d), dir: d === dr ? "right" : d === db ? "bottom" : "left", el: el.tagName.toLowerCase() + "." + [...el.classList].join(".") + " «" + (el.textContent || "").trim().slice(0, 40) + "»" };
          });
          if (worst) out.push(`${kind}#${fi} overflows ${worst.dir} by ${worst.d}px: ${worst.el}`);
          // text clipped inside fixed boxes (horizontal)
          scr.querySelectorAll(".btn, .pill, .chip, .n2-pin, .seg > *").forEach((el) => {
            if (el.scrollWidth > el.clientWidth + 2) out.push(`${kind}#${fi} clipped ${el.className} «${el.textContent.trim().slice(0, 30)}»`);
          });
        });
        return out;
      }, { id: s.id, o });
      if (res.length) console.log(`[${mode}] ${s.id} ${o}:\n  ` + res.join("\n  "));
      if (shots && mode === shots) {
        const el = await pg.$(`#${s.id} .ax-opt[data-opt="${o}"] .ax-pair`);
        if (el) await el.screenshot({ path: `/private/tmp/claude-501/-Users-naib-Documents-code/d0db8b41-ca1b-4be0-8c78-20704eb58cf7/scratchpad/shots/${s.id}-${o}-${mode}.png` });
      }
    }
  }
  if (errs.length) console.log(`[${mode}] console:\n  ` + errs.join("\n  "));
  await ctx.close();
}
await browser.close();
console.log("done");

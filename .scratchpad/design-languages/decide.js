// Decision helper for the "choose" pages. Include after review-bar.js:
//   <script src="decide.js"></script>
//
// Mark up each product surface as:
//   <section class="dc-surface" data-surface="strategies/list" data-title="Strategies list"
//            data-area="Strategies" data-why="One line on what this screen is for.">
//     <div class="dc-opt" data-opt="A" data-name="Split list and detail" data-rec
//          data-note="Idea, trade-off and build cost in one or two sentences.">
//       ...desktop frame and phone frame...
//     </div>
//     <div class="dc-opt" data-opt="B" data-name="Ledger table" data-note="...">...</div>
//   </section>
//
// It shows one option at a time with tabs, a "Pick this" button and a progress count, and keeps
// picks in localStorage under "lt-decide" (shared by every choose page and decide.html).
// Keys: left and right switch options, P picks, J and K move between surfaces.
(function () {
    const KEY = "lt-decide";
    const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } };
    const write = (v) => { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } };

    const css = `
.dc-surface { scroll-margin-top: 90px; padding: 40px 0 56px; border-top: 1px solid color-mix(in srgb, currentColor 12%, transparent); }
.dc-head { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; margin-bottom: 6px; }
.dc-head h2 { margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -0.01em; }
.dc-head .dc-area { font: 500 12px var(--font-mono, ui-monospace, monospace); opacity: 0.55; text-transform: uppercase; letter-spacing: 0.06em; }
.dc-head .dc-state { margin-left: auto; font: 500 12px var(--font-mono, ui-monospace, monospace); opacity: 0.7; }
.dc-head .dc-state b { color: var(--p-acc, var(--acc, currentColor)); }
.dc-why { margin: 0 0 16px; opacity: 0.7; max-width: 760px; }
.dc-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
.dc-tabs button { font: inherit; font-size: 14px; color: inherit; background: transparent; border: 1px solid color-mix(in srgb, currentColor 18%, transparent); border-radius: 999px; padding: 6px 12px; cursor: pointer; }
.dc-tabs button[aria-selected="true"] { background: color-mix(in srgb, currentColor 10%, transparent); border-color: color-mix(in srgb, currentColor 35%, transparent); }
.dc-tabs button .dc-k { font-family: var(--font-mono, ui-monospace, monospace); opacity: 0.6; margin-right: 6px; }
.dc-tabs button .dc-rec { font-size: 11px; margin-left: 6px; color: var(--p-acc, var(--acc, currentColor)); }
.dc-tabs button .dc-picked { margin-left: 6px; color: var(--p-acc, var(--acc, currentColor)); }
.dc-opt { display: none; }
.dc-opt.dc-on { display: block; }
.dc-foot { display: flex; align-items: center; gap: 14px; margin-top: 16px; flex-wrap: wrap; }
.dc-foot p { margin: 0; opacity: 0.75; max-width: 820px; flex: 1 1 420px; }
.dc-pick { font: inherit; font-weight: 600; border-radius: 8px; padding: 9px 16px; cursor: pointer; border: 1px solid var(--p-acc, var(--acc, currentColor)); background: transparent; color: var(--p-acc, var(--acc, currentColor)); }
.dc-pick[aria-pressed="true"] { background: var(--p-acc, var(--acc, currentColor)); color: var(--p-acc-ink, var(--acc-ink, #fff)); }
.dc-dock { position: fixed; right: 16px; bottom: 16px; z-index: 55; display: flex; gap: 10px; align-items: center; padding: 8px 10px 8px 14px; border-radius: 12px; font: 500 13px system-ui, sans-serif;
  background: color-mix(in srgb, var(--p-bg, #111) 92%, transparent); color: var(--p-ink, inherit); border: 1px solid color-mix(in srgb, currentColor 14%, transparent); box-shadow: 0 16px 40px -18px rgba(0,0,0,0.5); backdrop-filter: blur(8px); }
.dc-dock a, .dc-dock button { font: inherit; color: inherit; background: none; border: 0; cursor: pointer; padding: 4px 6px; border-radius: 6px; text-decoration: none; }
.dc-dock a:hover, .dc-dock button:hover { background: color-mix(in srgb, currentColor 10%, transparent); }
.dc-dock .dc-bar { width: 90px; height: 4px; border-radius: 4px; background: color-mix(in srgb, currentColor 15%, transparent); overflow: hidden; }
.dc-dock .dc-bar i { display: block; height: 100%; background: var(--p-acc, var(--acc, currentColor)); }
@media (max-width: 640px) { .dc-dock { left: 10px; right: 10px; justify-content: space-between; } .dc-head .dc-state { margin-left: 0; width: 100%; } }
`;
    const st = document.createElement("style");
    st.textContent = css;
    document.head.appendChild(st);

    const surfaces = [...document.querySelectorAll(".dc-surface")];
    let picks = read();

    function render(sec) {
        const id = sec.dataset.surface;
        const opts = [...sec.querySelectorAll(":scope > .dc-opt")];
        if (!opts.length) return;
        if (!sec.dcInit) {
            const head = document.createElement("div");
            head.className = "dc-head";
            head.innerHTML = `<h2>${sec.dataset.title || id}</h2><span class="dc-area">${sec.dataset.area || ""}</span><span class="dc-state"></span>`;
            const why = document.createElement("p");
            why.className = "dc-why";
            why.textContent = sec.dataset.why || "";
            const tabs = document.createElement("div");
            tabs.className = "dc-tabs";
            tabs.setAttribute("role", "tablist");
            opts.forEach((o) => {
                const b = document.createElement("button");
                b.type = "button";
                b.setAttribute("role", "tab");
                b.dataset.opt = o.dataset.opt;
                b.innerHTML = `<span class="dc-k">${o.dataset.opt}</span>${o.dataset.name || ""}${o.hasAttribute("data-rec") ? '<span class="dc-rec">recommended</span>' : ""}<span class="dc-picked"></span>`;
                b.addEventListener("click", () => show(sec, o.dataset.opt));
                tabs.appendChild(b);
            });
            const foot = document.createElement("div");
            foot.className = "dc-foot";
            foot.innerHTML = `<p class="dc-note"></p><button type="button" class="dc-pick" aria-pressed="false">Pick this</button>`;
            foot.querySelector(".dc-pick").addEventListener("click", () => pick(sec));
            sec.prepend(head, why, tabs);
            sec.appendChild(foot);
            sec.dcInit = true;
            const rec = opts.find((o) => o.hasAttribute("data-rec"));
            sec.dcCur = picks[id] && opts.some((o) => o.dataset.opt === picks[id]) ? picks[id] : (rec || opts[0]).dataset.opt;
        }
        const cur = sec.dcCur;
        opts.forEach((o) => o.classList.toggle("dc-on", o.dataset.opt === cur));
        sec.querySelectorAll(".dc-tabs button").forEach((b) => {
            b.setAttribute("aria-selected", String(b.dataset.opt === cur));
            b.querySelector(".dc-picked").textContent = picks[id] === b.dataset.opt ? " ✓" : "";
        });
        const on = opts.find((o) => o.dataset.opt === cur);
        sec.querySelector(".dc-note").textContent = on.dataset.note || "";
        const btn = sec.querySelector(".dc-pick");
        const picked = picks[id] === cur;
        btn.setAttribute("aria-pressed", String(picked));
        btn.textContent = picked ? "Picked" : "Pick this";
        const chosen = opts.find((o) => o.dataset.opt === picks[id]);
        sec.querySelector(".dc-state").innerHTML = chosen ? `Picked <b>${chosen.dataset.opt} · ${chosen.dataset.name}</b>` : "Not decided";
    }
    function show(sec, opt) { sec.dcCur = opt; render(sec); }
    function pick(sec) {
        const id = sec.dataset.surface;
        picks = read();
        let meta = {};
        try { meta = JSON.parse(localStorage.getItem(KEY + "-meta") || "{}"); } catch (e) { meta = {}; }
        if (picks[id] === sec.dcCur) { delete picks[id]; delete meta[id]; }
        else {
            picks[id] = sec.dcCur;
            const o = sec.querySelector(`:scope > .dc-opt[data-opt="${sec.dcCur}"]`);
            meta[id] = { title: sec.dataset.title || id, area: sec.dataset.area || "", name: o ? o.dataset.name || "" : "", note: o ? o.dataset.note || "" : "", rec: !!(o && o.hasAttribute("data-rec")), page: location.pathname.split("/").pop(), anchor: sec.id || "" };
        }
        write(picks);
        try { localStorage.setItem(KEY + "-meta", JSON.stringify(meta)); } catch (e) { /* storage unavailable */ }
        render(sec);
        dock();
    }
    surfaces.forEach(render);

    const d = document.createElement("div");
    d.className = "dc-dock";
    document.body.appendChild(d);
    function dock() {
        const n = surfaces.filter((s) => picks[s.dataset.surface]).length;
        const next = surfaces.find((s) => !picks[s.dataset.surface]);
        d.innerHTML = `<span>${n} of ${surfaces.length} decided</span><span class="dc-bar"><i style="width:${surfaces.length ? (100 * n) / surfaces.length : 0}%"></i></span>${next ? `<a href="#${next.id || ""}" data-next>Next undecided</a>` : ""}<a href="decide.html">All picks</a>`;
        const a = d.querySelector("[data-next]");
        if (a && next) {
            if (!next.id) next.id = next.dataset.surface.replace(/[^a-z0-9]+/gi, "-");
            a.setAttribute("href", "#" + next.id);
        }
    }
    dock();

    function current() {
        const mid = window.innerHeight * 0.35;
        return surfaces.find((s) => { const r = s.getBoundingClientRect(); return r.top <= mid && r.bottom > mid; }) || surfaces[0];
    }
    document.addEventListener("keydown", (e) => {
        if (e.target.closest("input, textarea, select, [contenteditable]") || e.metaKey || e.ctrlKey || e.altKey) return;
        const sec = current();
        if (!sec) return;
        const opts = [...sec.querySelectorAll(":scope > .dc-opt")].map((o) => o.dataset.opt);
        const i = opts.indexOf(sec.dcCur);
        if (e.key === "ArrowRight") { show(sec, opts[(i + 1) % opts.length]); e.preventDefault(); }
        else if (e.key === "ArrowLeft") { show(sec, opts[(i - 1 + opts.length) % opts.length]); e.preventDefault(); }
        else if (e.key === "p" || e.key === "P") pick(sec);
        else if (e.key === "j" || e.key === "k") {
            const j = surfaces.indexOf(sec) + (e.key === "j" ? 1 : -1);
            if (surfaces[j]) surfaces[j].scrollIntoView({ behavior: "smooth", block: "start" });
        }
    });
})();

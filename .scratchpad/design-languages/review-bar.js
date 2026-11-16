// Shared review bar for the LlamaTrade design pages. Include once, at the end of <body>:
//   <script src="review-bar.js"></script>
// It inserts a slim bar at the top of the page with a page switcher and, where the page
// supports them, Theme, Accent, Art and Logo controls. Settings are kept in localStorage.
(function () {
    const PAGES = [
        ["Overview", "index.html"],
        ["Site", "b-session-site.html"],
        ["Screens", "app-screens.html"],
        ["Flows", null, [["Auth, onboarding, home", "flow-auth-onboarding-home.html"], ["Library and builder", "flow-library-builder.html"], ["Backtests and sessions", "flow-backtests-sessions.html"], ["Portfolio, copilot, account", "flow-portfolio-copilot-account.html"]]],
        ["Choose", null, [["All picks", "decide.html"], ["Start, home, account", "choose-start-home-account.html"], ["Strategies and builder", "choose-strategies.html"], ["Backtests and sessions", "choose-backtests-sessions.html"], ["Shell, portfolio, copilot", "choose-shell-portfolio-copilot.html"]]],
        ["Logos", null, [["Marks", "logos.html"], ["Nav lockups", "logo-lockups.html"]]],
    ];
    const B_ACC = [["silver", "Silver", "#a1a1aa"], ["white", "Frost", "#dbe3f0"], ["orange", "Orange", "#ff9f43"], ["amber", "Amber", "#ffc24b"], ["lime", "Lime", "#d9f05c"], ["teal", "Teal", "#2dd4bf"], ["cyan", "Cyan", "#4cc2ff"], ["blue", "Blue", "#2563eb"], ["slate", "Slate blue", "#475f8a"], ["indigo", "Indigo", "#818cf8"], ["violet", "Violet", "#a78bfa"], ["lilac", "Lilac", "#d8b4fe"], ["pink", "Pink", "#f472b6"]];
    const C_ACC = [["iris", "Iris", "#4a3fd4"], ["ink", "Ink", "#18181b"], ["navy", "Navy", "#1f3d6b"], ["blue", "Blue", "#2563eb"], ["teal", "Pine", "#1d5c45"], ["amber", "Amber", "#b45309"]];
    const A_ACC = [["navy", "Navy", "#1f3b73"], ["ocean", "Ocean", "#1d4e89"], ["deepocean", "Deep ocean", "#113a72"], ["cobalt", "Cobalt", "#1e47a8"], ["denim", "Denim", "#2f5a96"], ["harbor", "Harbor", "#24507a"], ["prussian", "Prussian", "#0f3554"], ["ink", "Midnight", "#1b2940"], ["twilight", "Twilight", "#33437a"], ["indigonavy", "Indigo navy", "#2a3a8c"], ["steel", "Steel", "#3b5573"], ["slate", "Slate blue", "#475f8a"]];
    // Colour families for the site pages: [key, label, colour, fill, ink, generated]. Generated keys get their CSS from here.
    const FAM = {
        dark: [
            ["Blues", [["slate", "Slate blue", "#8fa4cf"], ["blue", "Blue", "#5b8cff"], ["cyan", "Cyan", "#4cc2ff"], ["indigo", "Indigo", "#818cf8"], ["sky", "Sky", "#7cb4ff", 0, "#04121c", 1], ["steelblue", "Steel", "#9fb3c8", 0, "#0b1220", 1], ["periwinkle", "Periwinkle", "#a5b4fc", 0, "#0b0b2e", 1], ["denim", "Denim", "#7fa0d4", "#2f5a96", "#ffffff", 1], ["navyglow", "Navy", "#8aa0e0", "#1f3b73", "#ffffff", 1]]],
            ["Greens", [["teal", "Teal", "#2dd4bf"], ["mint", "Mint", "#6ee7b7", 0, "#022c22", 1], ["emerald", "Emerald", "#34d399", 0, "#022c22", 1], ["jade", "Jade", "#3fbf8f", "#1f7a5a", "#ffffff", 1], ["forest", "Forest", "#7fbf9a", "#1f5c45", "#ffffff", 1], ["sage", "Sage", "#a3c9a8", 0, "#0f1a12", 1], ["moss", "Moss", "#b5c97a", 0, "#141a00", 1], ["lime", "Lime", "#d9f05c"]]],
            ["Neutrals", [["white", "Frost", "#dbe3f0"], ["snow", "Snow", "#f4f4f5", 0, "#0a0a0a", 1], ["silver", "Silver", "#a1a1aa"], ["ash", "Ash", "#c4c8ce", 0, "#0a0a0a", 1], ["graphite", "Graphite", "#9aa1aa", "#3a3f47", "#ffffff", 1], ["smoke", "Smoke", "#7d848e", 0, "#0a0a0a", 1]]],
            ["Warm", [["orange", "Orange", "#ff9f43"], ["amber", "Amber", "#ffc24b"], ["coral", "Coral", "#ff8a7a", 0, "#2b0a06", 1], ["rose", "Rose", "#fb7185", 0, "#2b0618", 1], ["pink", "Pink", "#f472b6"], ["violet", "Violet", "#a78bfa"], ["lilac", "Lilac", "#d8b4fe"]]],
        ],
        light: [
            ["Blues", [["ocean", "Ocean", "#1d4e89"], ["navy", "Navy", "#1f3b73"], ["deepocean", "Deep ocean", "#113a72", 0, 0, 1], ["cobalt", "Cobalt", "#1e47a8", 0, 0, 1], ["denim", "Denim", "#2f5a96", 0, 0, 1], ["harbor", "Harbor", "#24507a", 0, 0, 1], ["prussian", "Prussian", "#0f3554", 0, 0, 1], ["ink", "Midnight", "#1b2940"], ["twilight", "Twilight", "#33437a", 0, 0, 1], ["indigonavy", "Indigo navy", "#2a3a8c", 0, 0, 1], ["steel", "Steel", "#3b5573", 0, 0, 1], ["slate", "Slate blue", "#475f8a"]]],
            ["Greens", [["pine", "Pine", "#1d5c45"], ["forest", "Forest", "#1f4d36", 0, 0, 1], ["emerald", "Emerald", "#0f6b4f", 0, 0, 1], ["jade", "Jade", "#0e7c66", 0, 0, 1], ["teal", "Teal", "#0f6b78"], ["spruce", "Spruce", "#23463f", 0, 0, 1], ["evergreen", "Evergreen", "#18412f", 0, 0, 1], ["sage", "Sage", "#4f6b5a", 0, 0, 1], ["moss", "Moss", "#4a5d23", 0, 0, 1], ["olive", "Olive", "#5b6234", 0, 0, 1]]],
            ["Neutrals", [["black", "Black", "#0a0a0a", 0, 0, 1], ["graphite", "Graphite", "#2b2f36", 0, 0, 1], ["charcoal", "Charcoal", "#3a3f47"], ["slategrey", "Slate grey", "#4b5563", 0, 0, 1], ["stone", "Stone", "#57534e", 0, 0, 1], ["smoke", "Smoke", "#6b7280", 0, 0, 1]]],
            ["Warm", [["rust", "Rust", "#a8520a"], ["brick", "Brick", "#8c2f1e", 0, 0, 1], ["cocoa", "Cocoa", "#5c3a21", 0, 0, 1], ["wine", "Wine", "#6e1f2e", 0, 0, 1], ["burgundy", "Burgundy", "#5a1e3c"], ["plum", "Plum", "#6b2d5c"], ["iris", "Iris", "#4a3fd4"]]],
        ],
    };
    const famCss = () => {
        const hex = (c, a) => { const n = parseInt(c.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };
        const out = [];
        FAM.dark.forEach(([, list]) => list.forEach(([k, , c, f, ink, gen]) => {
            if (!gen) return;
            const fill = f || c, i = ink || "#0a0a0a";
            out.push(`html:not([data-mode="light"])[data-acc="${k}"] { --p-acc: ${c}; --acc-fill: ${fill}; --p-acc-ink: ${i}; --p-acc-soft: ${hex(c, 0.16)}; --p-pin-ring: ${hex(c, 0.2)}; --a-acc: ${c}; --a-acc-ink: ${i}; --a-acc-soft: ${hex(c, 0.16)}; --art-ink: ${hex(c, 0.14)}; --acc: ${c}; --acc-ink: ${i}; --acc-soft: ${hex(c, 0.16)}; }`);
        }));
        FAM.light.forEach(([, list]) => list.forEach(([k, , c, , , gen]) => {
            if (!gen) return;
            out.push(`html[data-mode="light"][data-acc="${k}"] { --p-acc: ${c}; --acc-fill: ${c}; --p-acc-ink: #fff; --p-acc-soft: color-mix(in srgb, ${c} 10%, #fff); --p-pin-ring: color-mix(in srgb, ${c} 15%, transparent); --a-acc: ${c}; --a-acc-ink: #fff; --a-acc-soft: color-mix(in srgb, ${c} 10%, #fff); --a-hatch: color-mix(in srgb, ${c} 16%, transparent); --art-ink: color-mix(in srgb, ${c} 32%, transparent); --acc: ${c}; --acc-ink: #fff; --acc-soft: color-mix(in srgb, ${c} 10%, #fff); }`);
        }));
        return out.join("\n");
    };
    // Type systems for the marketing site, app screens and flows: [key, label, sans, mono, Google Fonts query, display weight, display tracking].
    const FONTS = [
        ["geist", "Geist + Geist Mono", '"Geist", system-ui, sans-serif', '"Geist Mono", ui-monospace, monospace', "family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600", 600, "-0.035em", null, "Sans + mono"],
        ["plex", "IBM Plex Sans + Mono", '"IBM Plex Sans", system-ui, sans-serif', '"IBM Plex Mono", ui-monospace, monospace', "family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600", 600, "-0.02em", null, "Sans + mono"],
        ["intertight", "Inter Tight + JetBrains Mono", '"Inter Tight", system-ui, sans-serif', '"JetBrains Mono", ui-monospace, monospace', "family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600", 600, "-0.018em", null, "Sans + mono"],
        ["space", "Space Grotesk + Space Mono", '"Space Grotesk", system-ui, sans-serif', '"Space Mono", ui-monospace, monospace', "family=Space+Grotesk:wght@400;500;600;700&family=Space+Mono:wght@400;700", 600, "-0.03em", null, "Sans + mono"],
        ["redhat", "Red Hat Display + Red Hat Mono", '"Red Hat Display", system-ui, sans-serif', '"Red Hat Mono", ui-monospace, monospace', "family=Red+Hat+Display:wght@400;500;600;700&family=Red+Hat+Mono:wght@400;500;600", 700, "-0.025em", null, "Sans + mono"],
        ["sora", "Sora + Fira Code", '"Sora", system-ui, sans-serif', '"Fira Code", ui-monospace, monospace', "family=Sora:wght@400;500;600;700&family=Fira+Code:wght@400;500;600", 600, "-0.035em", null, "Sans + mono"],
        ["manrope", "Manrope + DM Mono", '"Manrope", system-ui, sans-serif', '"DM Mono", ui-monospace, monospace', "family=Manrope:wght@400;500;600;700;800&family=DM+Mono:wght@400;500", 700, "-0.03em", null, "Sans + mono"],
        ["familjen", "Familjen Grotesk + Spline Sans Mono", '"Familjen Grotesk", system-ui, sans-serif', '"Spline Sans Mono", ui-monospace, monospace', "family=Familjen+Grotesk:wght@400;500;600;700&family=Spline+Sans+Mono:wght@400;500;600", 600, "-0.02em", null, "Sans + mono"],
        ["albert", "Albert Sans + Azeret Mono", '"Albert Sans", system-ui, sans-serif', '"Azeret Mono", ui-monospace, monospace', "family=Albert+Sans:wght@400;500;600;700&family=Azeret+Mono:wght@400;500;600", 600, "-0.03em", null, "Sans + mono"],
        ["fragment", "Hanken Grotesk + Fragment Mono", '"Hanken Grotesk", system-ui, sans-serif', '"Fragment Mono", ui-monospace, monospace', "family=Hanken+Grotesk:wght@400;500;600;700&family=Fragment+Mono", 600, "-0.03em", null, "Sans + mono"],
        ["chivo", "Chivo + Chivo Mono", '"Chivo", system-ui, sans-serif', '"Chivo Mono", ui-monospace, monospace', "family=Chivo:wght@400;500;600;700&family=Chivo+Mono:wght@400;500;600", 600, "-0.03em", null, "Sans + mono"],
        ["jetbrains", "JetBrains Mono", '"JetBrains Mono", ui-monospace, monospace', '"JetBrains Mono", ui-monospace, monospace', "family=JetBrains+Mono:wght@400;500;600;700", 700, "-0.045em", null, "Mono-forward"],
        ["martian", "Martian Mono", '"Martian Mono", ui-monospace, monospace', '"Martian Mono", ui-monospace, monospace', "family=Martian+Mono:wght@300;400;500;600", 600, "-0.06em", null, "Mono-forward"],
        ["commit", "Commit Mono", '"Commit Mono", ui-monospace, monospace', '"Commit Mono", ui-monospace, monospace', "https://cdn.jsdelivr.net/npm/@fontsource/commit-mono@5.3.0/index.css|https://cdn.jsdelivr.net/npm/@fontsource/commit-mono@5.3.0/700.css", 700, "-0.045em", null, "Mono-forward"],
        ["victor", "Victor Mono", '"Victor Mono", ui-monospace, monospace', '"Victor Mono", ui-monospace, monospace', "family=Victor+Mono:wght@400;500;600;700", 700, "-0.04em", null, "Mono-forward"],
        ["unbounded", "Unbounded headings, Geist body", '"Geist", system-ui, sans-serif', '"Geist Mono", ui-monospace, monospace', "family=Unbounded:wght@500;600&family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600", 500, "-0.03em", '"Unbounded", system-ui, sans-serif', "Display experiments"],
        ["vt323", "VT323 headings, Geist body", '"Geist", system-ui, sans-serif', '"Geist Mono", ui-monospace, monospace', "family=VT323&family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600", 400, "0em", '"VT323", ui-monospace, monospace', "Display experiments"],
    ];
    const FONT_DEF = "geist";
    // Per-page controls. A page can also set window.RB_CONFIG = { theme, accent } before this script.
    const CONFIG = {
        "choose-start-home-account.html": { fonts: true, theme: { key: "lts-theme-b2", def: "slate", opts: [["slate", "Slate"], ["black", "Black"]] }, accent: { key: "lts-acc-b5", def: "slate", opts: B_ACC } },
        "choose-strategies.html": { fonts: true, theme: { key: "lts-theme-b2", def: "slate", opts: [["slate", "Slate"], ["black", "Black"]] }, accent: { key: "lts-acc-b5", def: "slate", opts: B_ACC } },
        "choose-backtests-sessions.html": { fonts: true, theme: { key: "lts-theme-b2", def: "slate", opts: [["slate", "Slate"], ["black", "Black"]] }, accent: { key: "lts-acc-b5", def: "slate", opts: B_ACC } },
        "choose-shell-portfolio-copilot.html": { fonts: true, theme: { key: "lts-theme-b2", def: "slate", opts: [["slate", "Slate"], ["black", "Black"]] }, accent: { key: "lts-acc-b5", def: "slate", opts: B_ACC } },
        "b-session-site.html": { fonts: true, theme: { key: "lts-theme-b2", def: "slate", opts: [["slate", "Slate"], ["black", "Black"]] }, accent: { key: "lts-acc-b5", def: "slate", opts: B_ACC }, logo: true },
        "logos.html": { theme: { key: "lts-theme-b2", def: "slate", opts: [["slate", "Slate"], ["black", "Black"]] }, accent: { key: "lts-acc-b5", def: "slate", opts: B_ACC } },
        "app-screens.html": { fonts: true, theme: { key: "lts-theme-b2", def: "slate", opts: [["slate", "Slate"], ["black", "Black"]] }, accent: { key: "lts-acc-b5", def: "slate", opts: B_ACC } },
        "a-statement-site.html": { accent: { key: "lts-acc-a6", def: "ocean", opts: A_ACC } },
        "flow-auth-onboarding-home.html": { fonts: true, theme: { key: "lts-theme-b2", def: "slate", opts: [["slate", "Slate"], ["black", "Black"]] }, accent: { key: "lts-acc-b5", def: "slate", opts: B_ACC } },
        "flow-library-builder.html": { fonts: true, theme: { key: "lts-theme-b2", def: "slate", opts: [["slate", "Slate"], ["black", "Black"]] }, accent: { key: "lts-acc-b5", def: "slate", opts: B_ACC } },
        "flow-backtests-sessions.html": { fonts: true, theme: { key: "lts-theme-b2", def: "slate", opts: [["slate", "Slate"], ["black", "Black"]] }, accent: { key: "lts-acc-b5", def: "slate", opts: B_ACC } },
        "flow-portfolio-copilot-account.html": { fonts: true, theme: { key: "lts-theme-b2", def: "slate", opts: [["slate", "Slate"], ["black", "Black"]] }, accent: { key: "lts-acc-b5", def: "slate", opts: B_ACC } },
        "c-weights-site.html": { accent: { key: "lts-acc-c", def: "iris", opts: C_ACC } },
    };
    const file = (location.pathname.split("/").pop() || "index.html").toLowerCase();
    const LOGOS = typeof LTL !== "undefined" ? LTL : window.LTL;
    const cfg = Object.assign({}, CONFIG[file] || {}, window.RB_CONFIG || {});
    if (cfg.accent && cfg.accent.key === "lts-acc-b5") cfg.accent = Object.assign({}, cfg.accent, { opts: B_ACC });
    if (cfg.accent && cfg.accent.key === "lts-acc-a6") cfg.accent = Object.assign({}, cfg.accent, { opts: A_ACC });
    const html = document.documentElement;
    const read = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
    const store = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* storage unavailable */ } };

    const css = `
.rb, .rb * { box-sizing: border-box; }
.rb { --rb-bg: #f6f6f4; --rb-fg: #6f6f6f; --rb-strong: #2a2a2a; --rb-line: rgba(0,0,0,0.08); --rb-hover: rgba(0,0,0,0.05); --rb-pop: #ffffff;
  position: relative; z-index: 60; height: 34px; display: flex; align-items: center; gap: 14px; padding: 0 14px; background: var(--rb-bg); border-bottom: 1px solid var(--rb-line);
  font: 500 12px/1 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; color: var(--rb-fg); letter-spacing: 0; white-space: nowrap; }
.rb.dark { --rb-bg: #0c0c0c; --rb-fg: #7d7d7d; --rb-strong: #d6d6d6; --rb-line: rgba(255,255,255,0.07); --rb-hover: rgba(255,255,255,0.06); --rb-pop: #161616; }
.rb a { color: var(--rb-fg); text-decoration: none; }
.rb button { font: inherit; color: inherit; background: none; border: 0; cursor: pointer; padding: 0; }
.rb .rb-id { color: var(--rb-strong); font-weight: 600; }
.rb .rb-id span { color: var(--rb-fg); font-weight: 500; }
.rb .rb-pages { display: flex; align-items: center; gap: 2px; }
.rb .rb-pages > a, .rb .rb-pages > .rb-dd > button { padding: 5px 7px; border-radius: 5px; display: inline-block; }
.rb .rb-pages > a:hover, .rb .rb-pages > .rb-dd > button:hover { background: var(--rb-hover); color: var(--rb-strong); }
.rb [aria-current="page"], .rb .rb-cur > button { color: var(--rb-strong) !important; background: var(--rb-hover); }
.rb .rb-dd { position: relative; }
.rb .rb-pop { display: none; position: absolute; top: calc(100% + 6px); left: 0; min-width: 140px; padding: 5px; background: var(--rb-pop); border: 1px solid var(--rb-line); border-radius: 8px; box-shadow: 0 12px 30px -12px rgba(0,0,0,0.35); }
.rb .rb-dd.open > .rb-pop { display: block; }
.rb .rb-pop a, .rb .rb-pop button.rb-item { display: block; width: 100%; text-align: left; padding: 7px 9px; border-radius: 5px; }
.rb .rb-pop a:hover, .rb .rb-pop button.rb-item:hover { background: var(--rb-hover); color: var(--rb-strong); }
.rb .rb-right { margin-left: auto; display: flex; align-items: center; gap: 14px; }
.rb .rb-grp { display: flex; align-items: center; gap: 4px; }
.rb .rb-grp > em { font-style: normal; margin-right: 3px; opacity: 0.8; }
.rb .rb-seg { display: inline-flex; border: 1px solid var(--rb-line); border-radius: 999px; padding: 1px; }
.rb .rb-seg button { padding: 3px 8px; border-radius: 999px; }
.rb .rb-seg button[aria-pressed="true"] { background: var(--rb-hover); color: var(--rb-strong); }
.rb .rb-dot { width: 12px; height: 12px; border-radius: 50%; box-shadow: inset 0 0 0 1px rgba(127,127,127,0.35); }
.rb .rb-dot.rb-def { width: 16px; height: 16px; }
.rb [data-cur-fam="Blues"] .rb-dot:not([data-fam="Blues"]), .rb [data-cur-fam="Greens"] .rb-dot:not([data-fam="Greens"]), .rb [data-cur-fam="Neutrals"] .rb-dot:not([data-fam="Neutrals"]), .rb [data-cur-fam="Warm"] .rb-dot:not([data-fam="Warm"]) { display: none; }
.rb .rb-fam > button { min-width: 74px; text-align: left; }
.rb .rb-dot[aria-pressed="true"] { box-shadow: 0 0 0 2px var(--rb-bg), 0 0 0 3.5px var(--rb-fg); }
.rb .rb-dot:focus-visible, .rb button:focus-visible, .rb a:focus-visible { outline: 1.5px solid var(--rb-fg); outline-offset: 2px; }
.rb .rb-pop.right { left: auto; right: 0; }
.rb .rb-grph { display: block; padding: 8px 9px 3px; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.06em; opacity: 0.7; }
.rb .rb-pop button.rb-item[aria-pressed="true"] { color: var(--rb-strong); background: var(--rb-hover); }
html:not([data-mode="light"]):not([data-theme="light"]) .rb [data-kind="lightsub"], html[data-mode="dark"] .rb [data-kind="lightsub"], html[data-mode="light"] .rb [data-for="dark"], html:not([data-mode="light"]) .rb [data-for="light"], html[data-mode="light"] .rb [data-kind="theme"] { display: none !important; }
.rb .bg-ctl { position: static !important; display: flex !important; flex-direction: column; align-items: stretch; gap: 0; padding: 0 !important; background: none !important; box-shadow: none !important; opacity: 1 !important; transform: none !important; pointer-events: auto !important; font: inherit !important; color: inherit !important; }
.rb .bg-ctl > span { display: none; }
.rb .bg-ctl button { text-align: left; padding: 7px 9px !important; border-radius: 5px !important; background: none !important; color: var(--rb-fg) !important; }
.rb .bg-ctl button[aria-pressed="true"] { color: var(--rb-strong) !important; background: var(--rb-hover) !important; }
.rb .rb-sel { color: var(--rb-strong); }
.rb .rb-hide { opacity: 0.7; padding: 4px 6px; border-radius: 5px; }
.rb .rb-hide:hover { background: var(--rb-hover); opacity: 1; }
.rb .rb-more, .rb .rb-pagesel { display: none; }
.rb-tab { position: fixed; top: 0; right: 14px; z-index: 60; height: 20px; padding: 0 9px; border-radius: 0 0 6px 6px; border: 0; font: 500 11px -apple-system, system-ui, sans-serif; background: rgba(120,120,120,0.22); color: inherit; opacity: 0.6; cursor: pointer; backdrop-filter: blur(6px); }
.rb-tab:hover { opacity: 1; }
html.rb-collapsed .rb { display: none; }
html:not(.rb-collapsed) .rb-tab { display: none; }
@media (max-width: 760px) {
  .rb { gap: 8px; padding: 0 10px; }
  .rb .rb-id span, .rb .rb-pages { display: none; }
  .rb .rb-pagesel { display: block; }
  .rb .rb-right { gap: 8px; }
  .rb .rb-right > .rb-ctl { display: none; }
  .rb .rb-more { display: block; }
  .rb .rb-more .rb-pop { min-width: 210px; }
  .rb .rb-more .rb-pop .rb-ctl { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 8px 6px; }
  .rb .rb-more .rb-pop .rb-ctl + .rb-ctl { border-top: 1px solid var(--rb-line); }
  .rb .rb-more .rb-pop .rb-ctl .rb-pop { position: static; display: block; border: 0; box-shadow: none; padding: 0; max-height: 40vh; }
  .rb .rb-more .rb-pop .rb-ctl[data-kind="logo"] > button { display: none; }
}
`;
    const st = document.createElement("style");
    st.textContent = css;
    st.id = "rb-style";
    document.head.appendChild(st);

    // Remove any legacy review bars.
    document.querySelectorAll("body > .review, body > header.top").forEach((e) => e.remove());

    const bar = document.createElement("div");
    bar.className = "rb";
    bar.setAttribute("role", "region");
    bar.setAttribute("aria-label", "Design review controls");

    // The marketing site is one page in two modes: Light is the A design, Dark is the B design.
    const SITE_MODES = [["light", "Light"], ["dark", "Dark"]];
    const siteMode = file === "b-session-site.html" || file.startsWith("choose-");
    const curFile = file === "a-statement-site.html" ? "b-session-site.html" : file;
    const ACC_FOR = { dark: { key: "lts-acc-b5", def: "slate", opts: B_ACC }, light: { key: "lts-acc-a6", def: "ocean", opts: A_ACC } };
    const mode = () => (html.dataset.mode === "light" ? "light" : "dark");
    const cur = PAGES.find((p) => p[1] === curFile || (p[2] && p[2].some((s) => s[1] === curFile)));
    const curName = cur ? (cur[2] ? (cur[2].find((s) => s[1] === curFile) || [cur[0]])[0] : cur[0]) : "Pages";
    const pageLinks = PAGES.map(([n, h, sub]) => sub
        ? `<span class="rb-dd${sub.some((s) => s[1] === curFile) ? " rb-cur" : ""}"><button type="button" aria-haspopup="true">${sub.some((s) => s[1] === curFile) ? curName : n} ▾</button><span class="rb-pop">${sub.map(([sn, sh]) => `<a href="${sh}"${sh === curFile ? ' aria-current="page"' : ""}>${sn}</a>`).join("")}</span></span>`
        : `<a href="${h}"${h === curFile ? ' aria-current="page"' : ""}>${n}</a>`).join("");
    const flat = PAGES.flatMap(([n, h, sub]) => (sub ? sub : [[n === "A" || n === "B" || n === "C" ? n + ". direction" : n, h]]));
    const pageSel = `<span class="rb-dd rb-pagesel"><button type="button" class="rb-sel">${curName} ▾</button><span class="rb-pop">${flat.map(([n, h]) => `<a href="${h}"${h === curFile ? ' aria-current="page"' : ""}>${n}</a>`).join("")}</span></span>`;

    const ctl = [];
    if (siteMode) {
        ctl.push(`<span class="rb-grp rb-ctl" data-kind="mode"><span class="rb-seg">${SITE_MODES.map(([k, n]) => `<button type="button" data-rb-mode="${k}" aria-pressed="false">${n}</button>`).join("")}</span></span>`);
    }
    const hasLightTheme = siteMode || (cfg.theme && cfg.theme.opts.some((o) => o[0] === "light"));
    if (hasLightTheme) ctl.push(`<span class="rb-grp rb-ctl" data-kind="lightsub"><span class="rb-seg">${[["warm", "Warm"], ["white", "White"]].map(([k, n]) => `<button type="button" data-rb-light="${k}" aria-pressed="false">${n}</button>`).join("")}</span></span>`);
    if (cfg.theme) {
        const t = cfg.theme;
        ctl.push(`<span class="rb-grp rb-ctl" data-kind="theme"><span class="rb-seg">${t.opts.map(([k, n]) => `<button type="button" data-rb-th="${k}" aria-pressed="false">${n}</button>`).join("")}</span></span>`);
    }
    const dots = (opts, forMode, def) => `<span class="rb-grp rb-ctl" data-kind="accent"${forMode ? ` data-for="${forMode}"` : ""} role="group" aria-label="Accent">${opts.map(([k, n, c]) => `<button type="button" class="rb-dot${k === def ? " rb-def" : ""}" data-rb-acc="${k}" title="${n}${k === def ? " (default)" : ""}" aria-label="${n} accent" aria-pressed="false" style="background:${c}"></button>`).join("")}</span>`;
    const famDots = (m) => {
        const cur = read("lts-pal-" + m) || "Blues";
        const def = ACC_FOR[m].def;
        const menu = `<span class="rb-dd rb-ctl rb-fam" data-for="${m}"><button type="button" aria-haspopup="true" data-fam-label>${cur} ▾</button><span class="rb-pop right">${FAM[m].map(([f]) => `<button type="button" class="rb-item" data-rb-fam="${f}" data-fam-mode="${m}" aria-pressed="${f === cur}">${f}</button>`).join("")}</span></span>`;
        const btns = FAM[m].map(([f, list]) => list.map(([k, n, c]) => `<button type="button" class="rb-dot${k === def ? " rb-def" : ""}" data-fam="${f}" data-rb-acc="${k}" title="${n}${k === def ? " (default)" : ""}" aria-label="${n} accent" aria-pressed="false" style="background:${c}"></button>`).join("")).join("");
        return menu + `<span class="rb-grp rb-ctl" data-kind="accent" data-for="${m}" data-cur-fam="${cur}" role="group" aria-label="Accent">${btns}</span>`;
    };
    if (siteMode) {
        const st = document.createElement("style");
        st.textContent = famCss();
        document.head.appendChild(st);
        ctl.push(famDots("dark"), famDots("light"));
    }
    else if (cfg.accent) {
        ctl.push(`<span class="rb-grp rb-ctl" data-kind="accent" role="group" aria-label="Accent">${cfg.accent.opts.map(([k, n, c]) => `<button type="button" class="rb-dot" data-rb-acc="${k}" title="${n}" aria-label="${n} accent" aria-pressed="false" style="background:${c}"></button>`).join("")}</span>`);
    }
    const hasArt = !!document.querySelector(".bg-ctl") || !!document.querySelector("[data-hero-art]");
    if (hasArt) ctl.push(`<span class="rb-dd rb-ctl" data-kind="art"><button type="button" class="rb-artbtn" aria-haspopup="true">Art ▾</button><span class="rb-pop right rb-artpop"></span></span>`);
    const hasLogo = cfg.logo && LOGOS;
    if (cfg.fonts) ctl.push(`<span class="rb-dd rb-ctl" data-kind="font"><button type="button" aria-haspopup="true">Font ▾</button><span class="rb-pop right" style="max-height:70vh;overflow:auto;min-width:250px">${FONTS.map((f, i) => (i === 0 || FONTS[i - 1][8] !== f[8] ? `<span class="rb-grph">${f[8]}</span>` : "") + `<button type="button" class="rb-item" data-rb-font="${f[0]}" aria-pressed="false">${f[1]}${f[0] === FONT_DEF ? " · pick" : ""}</button>`).join("")}</span></span>`);
    if (hasLogo) {
        const L = LOGOS;
        const ids = ["current"].concat((L.families || []).flatMap((f) => f.ids));
        ctl.push(`<span class="rb-dd rb-ctl" data-kind="logo"><button type="button" aria-haspopup="true">Logo ▾</button><span class="rb-pop right" style="max-height:60vh;overflow:auto">${ids.map((id) => `<button type="button" class="rb-item" data-rb-logo="${id}">${L.marks[id].name}</button>`).join("")}</span></span>`);
    }

    bar.innerHTML = `<span class="rb-id">LlamaTrade <span>· design</span></span><nav class="rb-pages" aria-label="Design pages">${pageLinks}</nav>${pageSel}
        <span class="rb-right">${ctl.join("")}${ctl.length ? `<span class="rb-dd rb-more"><button type="button" aria-haspopup="true">Controls ▾</button><span class="rb-pop right"></span></span>` : ""}<button type="button" class="rb-hide" title="Hide this bar" aria-label="Hide the review bar">✕</button></span>`;
    document.body.prepend(bar);
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "rb-tab";
    tab.textContent = "Design ▾";
    tab.setAttribute("aria-label", "Show the review bar");
    document.body.appendChild(tab);

    // Phone: clone the controls into the Controls menu, wired to the same handlers below.
    const more = bar.querySelector(".rb-more .rb-pop");
    if (more) bar.querySelectorAll(".rb-right > .rb-ctl").forEach((c) => { if (c.dataset.kind !== "art") more.appendChild(c.cloneNode(true)); });
    if (more && !more.children.length) more.parentElement.remove();
    const art = document.querySelector(".bg-ctl");
    const heroHost = document.querySelector("[data-hero-art]");
    if (heroHost) {
        const pop = bar.querySelector(".rb-artpop");
        pop.insertAdjacentHTML("afterbegin", [["charts", "Hero: charts"], ["full", "Hero: full chart"], ["minimal", "Hero: minimal"], ["none", "Hero: none"]].map(([k, n]) => `<button type="button" class="rb-item" data-rb-hero="${k}" aria-pressed="false">${n}</button>`).join("") + '<span style="display:block;height:1px;margin:4px 6px;background:var(--rb-line)"></span>');
        setHero(html.dataset.hero || read("lts-hero-art") || "charts");
        pop.insertAdjacentHTML("afterbegin", '<span class="rb-grph">Dividers</span>' + [["axis", "Price axis"], ["index", "Section index"], ["spark", "Sparkline"], ["fade", "Faded hairline"]].map(([k, n]) => `<button type="button" class="rb-item" data-rb-div="${k}" aria-pressed="false">${n}</button>`).join("") + '<span class="rb-grph">Hero</span>');
        setDiv(html.dataset.div || read("lts-dividers") || "axis");
    }
    if (art) {
        bar.querySelector(".rb-artpop").appendChild(art);
    }

    function tone() {
        const c = getComputedStyle(document.body).backgroundColor !== "rgba(0, 0, 0, 0)" ? getComputedStyle(document.body).backgroundColor : getComputedStyle(html).backgroundColor;
        const m = c.match(/\d+(\.\d+)?/g);
        const lum = m ? (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255 : 1;
        bar.classList.toggle("dark", lum < 0.4);
        tab.style.color = lum < 0.4 ? "#bbb" : "#333";
    }
    function setTheme(v) {
        html.dataset.theme = v;
        store(cfg.theme.key, v);
        bar.querySelectorAll("[data-rb-th]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.rbTh === v));
        requestAnimationFrame(tone);
    }
    function setAcc(v) {
        html.dataset.acc = v;
        store(siteMode ? ACC_FOR[mode()].key : cfg.accent.key, v);
        bar.querySelectorAll(siteMode ? `[data-for="${mode()}"] [data-rb-acc]` : "[data-rb-acc]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.rbAcc === v));
    }
    function setMode(m) {
        html.dataset.mode = m;
        store("lts-site-mode", m);
        const a = ACC_FOR[m];
        setAcc(read(a.key) || a.def);
        bar.querySelectorAll("[data-rb-mode]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.rbMode === m));
        if (typeof LTS !== "undefined") {
            document.querySelectorAll("[data-heat]").forEach((h) => { delete h.dataset.done; h.innerHTML = ""; });
            LTS.mountCharts(document);
        }
        requestAnimationFrame(tone);
        window.dispatchEvent(new Event("resize"));
    }
    function setDiv(v) {
        html.dataset.div = v;
        store("lts-dividers", v);
        bar.querySelectorAll("[data-rb-div]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.rbDiv === v));
    }
    function setHero(v) {
        html.dataset.hero = v;
        store("lts-hero-art", v);
        bar.querySelectorAll("[data-rb-hero]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.rbHero === v));
    }
    // Fonts: rewrite every literal font family in the page's own CSS to two variables once, then switch the variables.
    function rewriteFonts() {
        const fam = /(["'][^"']+["'](?:\s*,\s*(?:["'][^"']+["']|[\w-]+))*)\s*(!important)?\s*$/;
        const fix = (decl) => {
            for (let i = decl.length - 1; i >= 0; i--) {
                const p = decl[i];
                if (p === "font-family") {
                    const ff = decl.getPropertyValue("font-family");
                    if (ff && !/var\(/.test(ff) && !/apple-system/.test(ff)) decl.setProperty("font-family", /mono|courier/i.test(ff) ? "var(--font-mono)" : "var(--font-sans)", decl.getPropertyPriority("font-family"));
                    continue;
                }
                if (!(p.startsWith("--") && /font|sans|mono|serif|display|body|num|head|code|kicker|cap/.test(p))) continue;
                const v = decl.getPropertyValue(p);
                const m = v.match(fam);
                if (!m || /var\(--font-/.test(v)) continue;
                const mono = /mono|courier/i.test(m[1]);
                decl.setProperty(p, v.slice(0, m.index) + (mono ? "var(--font-mono)" : "var(--font-sans)"), decl.getPropertyPriority(p));
            }
        };
        const walk = (rules) => { for (const r of rules) { if (r.style) fix(r.style); if (r.cssRules) walk(r.cssRules); } };
        for (const sh of document.styleSheets) {
            if (sh.ownerNode && sh.ownerNode.id === "rb-style") continue;
            try { walk(sh.cssRules); } catch (e) { /* cross-origin sheet */ }
        }
        document.querySelectorAll("[style*='font']").forEach((e) => { if (!bar.contains(e)) fix(e.style); });
    }
    function setFont(k) {
        const f = FONTS.find((x) => x[0] === k) || FONTS.find((x) => x[0] === FONT_DEF);
        html.dataset.font = f[0];
        store("lts-font", f[0]);
        document.querySelectorAll("link[data-rb-font]").forEach((l) => l.remove());
        const urls = f[4].startsWith("http") ? f[4].split("|") : ["https://fonts.googleapis.com/css2?" + f[4] + "&display=swap"];
        urls.forEach((u) => { const l = document.createElement("link"); l.rel = "stylesheet"; l.href = u; l.setAttribute("data-rb-font", ""); document.head.appendChild(l); });
        html.style.setProperty("--font-display", f[7] || f[2]);
        html.style.setProperty("--font-sans", f[2]);
        html.style.setProperty("--font-mono", f[3]);
        html.style.setProperty("--p-display-w", String(f[5]));
        html.style.setProperty("--p-display-ls", f[6]);
        [["--p-display", "display"], ["--p-body", "sans"], ["--a-font", "sans"], ["--a-head", "sans"], ["--sans", "sans"], ["--p-num", "mono"], ["--a-num", "mono"], ["--a-num-big", "mono"], ["--a-code", "mono"], ["--mono", "mono"], ["--art-font", "mono"], ["--art-mono", "mono"]].forEach(([v, t]) => html.style.setProperty(v, `var(--font-${t})`));
        html.style.setProperty("--p-kicker-font", "500 13px var(--font-mono)");
        html.style.setProperty("--p-cap-font", "500 13px var(--font-mono)");
        bar.querySelectorAll("[data-rb-font]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.rbFont === f[0]));
        if (document.fonts) document.fonts.ready.then(() => { if (typeof LTS !== "undefined" && LTS.fitAll) LTS.fitAll(); window.dispatchEvent(new Event("resize")); });
    }
    function setLight(v) {
        html.dataset.light = v === "white" ? "white" : "warm";
        store("lts-light-sub2", html.dataset.light);
        bar.querySelectorAll("[data-rb-light]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.rbLight === html.dataset.light));
        requestAnimationFrame(tone);
    }
    function setLogo(id) {
        store("lts-logo-v2", id);
        document.querySelectorAll("header .logo, .nav .logo, footer .logo").forEach((e) => (e.innerHTML = LOGOS.lockup(id)));
        bar.querySelectorAll("[data-rb-logo]").forEach((b) => (b.style.fontWeight = b.dataset.rbLogo === id ? "700" : ""));
    }
    if (cfg.theme) setTheme(html.dataset.theme || read(cfg.theme.key) || cfg.theme.def);
    if (cfg.fonts) {
        const fst = document.createElement("style");
        fst.textContent = "html[data-font] body { font-variant-numeric: tabular-nums; } html[data-font][data-mode] .facts b { font-family: var(--font-mono); font-weight: 500; } html[data-font][data-mode] .kicker { font-style: normal; } html[data-font][data-mode] .invite input[type=email] { font-family: var(--font-sans); font-size: 16px; } html[data-font=vt323] .hero h1 { font-size: 74px; line-height: 1; } html[data-font=vt323] .sec-h h2, html[data-font=vt323] .split h2, html[data-font=vt323] .cta h2 { font-size: 58px; line-height: 1; } @media (max-width: 700px) { html[data-font=vt323] .hero h1 { font-size: 48px; } html[data-font=vt323] .sec-h h2, html[data-font=vt323] .split h2, html[data-font=vt323] .cta h2 { font-size: 40px; } } @media (max-width: 700px) { html[data-font=martian] .nav .btn, html[data-font=victor] .nav .btn, html[data-font=commit] .nav .btn { font-size: 12.5px; padding: 0 11px; letter-spacing: -0.02em; } }";
        document.head.appendChild(fst);
        rewriteFonts();
        setFont(read("lts-font") || FONT_DEF);
    }
    if (hasLightTheme) setLight(read("lts-light-sub2") || "white");
    if (siteMode) setMode(mode());
    else if (cfg.accent) setAcc(html.dataset.acc || read(cfg.accent.key) || cfg.accent.def);
    if (hasLogo) { const s = read("lts-logo-v2"); bar.querySelectorAll("[data-rb-logo]").forEach((b) => (b.style.fontWeight = b.dataset.rbLogo === (s && LOGOS.marks[s] ? s : "bc-candle") ? "700" : "")); }

    bar.addEventListener("click", (e) => {
        const t = e.target.closest("button");
        if (!t) return;
        if (t.dataset.rbTh) return setTheme(t.dataset.rbTh);
        if (t.dataset.rbAcc) return setAcc(t.dataset.rbAcc);
        if (t.dataset.rbFam) {
            const m = t.dataset.famMode, f = t.dataset.rbFam;
            store("lts-pal-" + m, f);
            document.querySelectorAll(`[data-kind="accent"][data-for="${m}"]`).forEach((g) => (g.dataset.curFam = f));
            document.querySelectorAll(`.rb-fam[data-for="${m}"] [data-fam-label]`).forEach((b) => (b.textContent = f + " ▾"));
            document.querySelectorAll(`[data-fam-mode="${m}"]`).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.rbFam === f)));
            return;
        }
        if (t.dataset.rbLight) return setLight(t.dataset.rbLight);
        if (t.dataset.rbFont) { setFont(t.dataset.rbFont); return t.closest(".rb-dd").classList.remove("open"); }
        if (t.dataset.rbMode) return setMode(t.dataset.rbMode);
        if (t.dataset.rbHero) return setHero(t.dataset.rbHero);
        if (t.dataset.rbDiv) return setDiv(t.dataset.rbDiv);
        if (t.dataset.rbLogo) { setLogo(t.dataset.rbLogo); return t.closest(".rb-dd").classList.remove("open"); }
        if (t.classList.contains("rb-hide")) { html.classList.add("rb-collapsed"); store("lts-rb-collapsed", "1"); return; }
        const dd = t.parentElement.classList.contains("rb-dd") ? t.parentElement : null;
        if (dd && t === dd.firstElementChild) {
            const was = dd.classList.contains("open");
            bar.querySelectorAll(".rb-dd.open").forEach((d) => { if (!d.contains(dd)) d.classList.remove("open"); });
            dd.classList.toggle("open", !was);
            e.stopPropagation();
        }
    });
    document.addEventListener("click", (e) => { if (!bar.contains(e.target)) bar.querySelectorAll(".rb-dd.open").forEach((d) => d.classList.remove("open")); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") bar.querySelectorAll(".rb-dd.open").forEach((d) => d.classList.remove("open")); });
    tab.addEventListener("click", () => { html.classList.remove("rb-collapsed"); store("lts-rb-collapsed", ""); });
    if (read("lts-rb-collapsed") === "1") html.classList.add("rb-collapsed");
    tone();
    if (document.fonts) document.fonts.ready.then(tone, tone);
})();

// Ticker tape data for the LlamaTrade marketing site.
// Fetches the ticker snapshot JSON (see ticker-endpoint.md for the shape), keeps the last good
// response in localStorage, and renders it into a .tape element. Exposes window.LTTicker.
(function () {
    const STORE_KEY = "lt-ticker-last-good";
    const FETCH_TIMEOUT_MS = 5000;
    const OPEN_REFRESH_MS = 60 * 1000;
    const CLOSED_REFRESH_MS = 15 * 60 * 1000;
    const ET = "America/New_York";

    // Shipped with the page so the tape never renders empty. Regenerated at build time.
    const BUILT_IN = {
        version: 1,
        generated_at: "2026-11-13T21:20:00Z",
        as_of: "2026-11-13T21:00:00Z",
        basis: "close",
        delay_minutes: null,
        session_date: "2026-11-13",
        market: { is_open: false, next_open: "2026-11-16T14:30:00Z", next_close: "2026-11-16T21:00:00Z" },
        source: { provider: "Built-in fallback", attribution: "", url: "" },
        quotes: [],
    };

    function isNum(v) {
        return typeof v === "number" && Number.isFinite(v);
    }

    function valid(d) {
        return !!d && d.version === 1 && typeof d.as_of === "string" && !Number.isNaN(Date.parse(d.as_of))
            && (d.basis === "close" || d.basis === "delayed" || d.basis === "realtime")
            && d.market && typeof d.market.is_open === "boolean"
            && d.source && typeof d.source.attribution === "string"
            && Array.isArray(d.quotes) && d.quotes.length > 0
            && d.quotes.every((q) => q && typeof q.symbol === "string" && isNum(q.price) && isNum(q.change) && isNum(q.change_pct));
    }

    function readStore() {
        try {
            const raw = localStorage.getItem(STORE_KEY);
            const d = raw ? JSON.parse(raw) : null;
            return valid(d) ? d : null;
        } catch (e) {
            return null;
        }
    }

    function writeStore(d) {
        try {
            localStorage.setItem(STORE_KEY, JSON.stringify(d));
        } catch (e) {
            // Storage is a convenience; the tape still renders without it.
        }
    }

    async function fetchSnapshot(url) {
        const ctl = new AbortController();
        const timer = setTimeout(() => ctl.abort(), FETCH_TIMEOUT_MS);
        try {
            const res = await fetch(url, { signal: ctl.signal, headers: { Accept: "application/json" } });
            if (!res.ok) throw new Error("HTTP " + res.status);
            const d = await res.json();
            if (!valid(d)) throw new Error("Unexpected ticker payload");
            return d;
        } finally {
            clearTimeout(timer);
        }
    }

    // Newest of: fresh fetch, last good in storage, built-in values.
    async function load(url, fallback) {
        try {
            const d = await fetchSnapshot(url);
            writeStore(d);
            return { data: d, fresh: true };
        } catch (err) {
            const stored = readStore();
            const base = fallback && valid(fallback) ? fallback : null;
            const pick = [stored, base].filter(Boolean).sort((a, b) => Date.parse(b.as_of) - Date.parse(a.as_of))[0];
            return { data: pick || null, fresh: false, error: err };
        }
    }

    const fmtPrice = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const fmtPct = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    function pct(v) {
        if (Math.abs(v) < 0.005) return "0.00%";
        return (v > 0 ? "+" : "−") + fmtPct.format(Math.abs(v)) + "%";
    }

    function dayLabel(dateStr) {
        // session_date is a plain date in New York; anchor it at noon UTC so it never shifts a day.
        const d = new Date(dateStr + "T12:00:00Z");
        return new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" }).format(d);
    }

    function timeLabel(iso) {
        return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone: ET }).format(new Date(iso))
            .replace("AM", "am").replace("PM", "pm") + " ET";
    }

    function etDate(iso) {
        return new Intl.DateTimeFormat("en-CA", { timeZone: ET }).format(new Date(iso));
    }

    // The label is derived from as_of, so old values stay correctly described after a failed refresh.
    function asOfLabel(d, now) {
        if (d.basis === "close") {
            return "As of " + dayLabel(d.session_date || etDate(d.as_of)) + " close";
        }
        const ageMin = (now - Date.parse(d.as_of)) / 60000;
        const sameDay = etDate(d.as_of) === etDate(new Date(now).toISOString());
        const when = sameDay ? timeLabel(d.as_of) : dayLabel(etDate(d.as_of)) + ", " + timeLabel(d.as_of);
        const delay = d.delay_minutes || 0;
        if (d.basis === "delayed" && ageMin <= delay + 10) return "Delayed " + delay + " min · " + when;
        if (d.basis === "realtime" && ageMin <= 5) return "Live · " + when;
        return "As of " + when;
    }

    function marketLabel(d, now) {
        const m = d.market;
        if (m.next_close && m.is_open && now >= Date.parse(m.next_close)) return { open: false, text: "Market closed" };
        if (!m.is_open && m.next_open && now >= Date.parse(m.next_open) && (!m.next_close || now < Date.parse(m.next_close))) {
            return { open: true, text: "Market open" };
        }
        return { open: m.is_open, text: m.is_open ? "Market open" : "Market closed" };
    }

    function el(tag, cls, text) {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text != null) e.textContent = text;
        return e;
    }

    function quoteNode(q) {
        const s = el("span", "q");
        s.dataset.sym = q.symbol;
        s.append(el("b", null, q.symbol), el("span", "p", fmtPrice.format(q.price)));
        const c = el("span", "c", pct(q.change_pct));
        c.dataset.dir = q.change_pct >= 0.005 ? "up" : q.change_pct <= -0.005 ? "down" : "flat";
        s.append(c);
        return s;
    }

    function metaNodes(d, now) {
        const mk = marketLabel(d, now);
        const state = el("span", "q meta state", mk.text);
        state.dataset.open = String(mk.open);
        const asof = el("span", "q meta asof", asOfLabel(d, now));
        const out = [state, asof];
        if (d.source.attribution) {
            const src = el("span", "q meta src");
            if (d.source.url) {
                const a = el("a", null, d.source.attribution);
                a.href = d.source.url;
                src.append(a);
            } else {
                src.textContent = d.source.attribution;
            }
            out.push(src);
        }
        return out;
    }

    // Renders two copies of the run so the CSS marquee loops without a gap.
    function render(tape, d, prev) {
        const now = Date.now();
        const inner = tape.querySelector(".in") || tape.appendChild(el("div", "in"));
        const prevPrice = new Map((prev ? prev.quotes : []).map((q) => [q.symbol, q.price]));
        const run = () => [...metaNodes(d, now), ...d.quotes.map(quoteNode)];
        inner.replaceChildren(...run(), ...run());
        inner.querySelectorAll(".q[data-sym]").forEach((n) => {
            const before = prevPrice.get(n.dataset.sym);
            const q = d.quotes.find((x) => x.symbol === n.dataset.sym);
            if (before != null && q && q.price !== before) n.classList.add(q.price > before ? "fu" : "fd");
        });
        tape.setAttribute("aria-label", "ETF prices, " + asOfLabel(d, now) + (d.source.attribution ? ". " + d.source.attribution : ""));
        tape.dataset.state = "ready";
    }

    function nextDelay(d) {
        const now = Date.now();
        if (d && marketLabel(d, now).open) return OPEN_REFRESH_MS;
        if (d && d.market.next_open) {
            // First delayed print after the open, but never sleep longer than the closed cadence.
            const wake = Date.parse(d.market.next_open) + ((d.delay_minutes || 15) + 1) * 60000 - now;
            if (wake > 0) return Math.min(wake, CLOSED_REFRESH_MS);
        }
        return CLOSED_REFRESH_MS;
    }

    // Mounts the tape: renders cached values first, then refreshes on a market-aware cadence.
    function mount(tape, opts) {
        const url = opts.url;
        const fallback = opts.fallback || BUILT_IN;
        let current = readStore() || (valid(fallback) ? fallback : null);
        let timer = null;
        if (current) render(tape, current, null);

        async function tick() {
            const r = await load(url, current || fallback);
            if (r.data) {
                const isNew = !current || r.data.as_of !== current.as_of || !r.fresh;
                if (isNew) render(tape, r.data, current);
                current = r.data;
            } else {
                tape.dataset.state = "empty";
            }
            tape.dataset.fresh = String(r.fresh);
            if (opts.onUpdate) opts.onUpdate(r);
            schedule();
        }

        function schedule() {
            clearTimeout(timer);
            if (document.hidden) return;
            timer = setTimeout(tick, nextDelay(current));
        }

        document.addEventListener("visibilitychange", () => {
            if (document.hidden) clearTimeout(timer);
            else tick();
        });
        tick();
        return { refresh: tick };
    }

    window.LTTicker = { mount, load, valid, asOfLabel, marketLabel, STORE_KEY };
})();

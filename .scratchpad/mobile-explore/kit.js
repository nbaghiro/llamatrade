/* LlamaTrade mobile explorations: shared viewer, phone, tablet and watch frames, iOS system UI fillers,
   picks (stored under axm-*, apart from the web playground) and chart helpers. No dependencies. */
(function () {
  "use strict";

  /* ------------------------------------------------------------ storage */
  const store = {
    raw(k) {
      try { return localStorage.getItem(k); } catch (e) { return null; }
    },
    get(k, d) {
      try {
        const v = localStorage.getItem(k);
        return v == null ? d : JSON.parse(v);
      } catch (e) { return d; }
    },
    set(k, v) {
      try { localStorage.setItem(k, typeof v === "string" ? v : JSON.stringify(v)); } catch (e) { /* storage blocked */ }
    },
  };
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /* ------------------------------------------------------------ mode */
  const osLight = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
  function currentMode() {
    const s = store.raw("ax-mode");
    if (s === "light" || s === "dark") return s;
    return osLight && osLight.matches ? "light" : "dark";
  }
  function setMode(m, save) {
    document.documentElement.dataset.mode = m;
    if (save) store.set("ax-mode", m);
    document.querySelectorAll(".ax-modes button").forEach((b) => b.classList.toggle("on", b.dataset.mode === m));
  }
  setMode(currentMode(), false);
  if (osLight && osLight.addEventListener) {
    osLight.addEventListener("change", () => { if (!store.raw("ax-mode")) setMode(currentMode(), false); });
  }

  /* ------------------------------------------------------------ icons and logo */
  const ICONS = {
    home: "M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z",
    strategies: "M12 3 3 7.5 12 12l9-4.5L12 3Z M3 12l9 4.5 9-4.5 M3 16.5 12 21l9-4.5",
    portfolio: "M12 3a9 9 0 1 0 9 9h-9z M15 3.3A9 9 0 0 1 20.7 9H15z",
    copilot: "M12 3c.6 4.2 2.8 6.4 7 7-4.2.6-6.4 2.8-7 7-.6-4.2-2.8-6.4-7-7 4.2-.6 6.4-2.8 7-7Z M19 15.5c.2 1.5 1 2.3 2.5 2.5-1.5.2-2.3 1-2.5 2.5-.2-1.5-1-2.3-2.5-2.5 1.5-.2 2.3-1 2.5-2.5Z",
    account: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z M4.5 20.5c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5",
    backtests: "M4 4v16h16 M7.5 15l4-4 3 3 5-6",
    sessions: "M3 12h4l2.5-6 5 12 2.5-6h4",
    bell: "M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15z M10 20.5a2 2 0 0 0 4 0",
    search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z M20 20l-4-4",
    plus: "M12 5v14 M5 12h14",
    minus: "M5 12h14",
    "arrow-right": "M5 12h14 M13 6l6 6-6 6",
    "arrow-left": "M19 12H5 M11 6l-6 6 6 6",
    "arrow-up-right": "M7 17 17 7 M9 7h8v8",
    "chevron-right": "m9 6 6 6-6 6",
    "chevron-left": "m15 6-6 6 6 6",
    "chevron-down": "m6 9 6 6 6-6",
    "chevron-up": "m6 15 6-6 6 6",
    check: "m5 12.5 4.5 4.5L19 7.5",
    x: "M6 6l12 12 M18 6 6 18",
    more: "M5.5 12h.01 M12 12h.01 M18.5 12h.01",
    sliders: "M4 7h10 M18 7h2 M4 17h2 M10 17h10 M16 5v4 M8 15v4",
    filter: "M4 6h16 M7 12h10 M10 18h4",
    play: "M8 5.5v13l10.5-6.5z",
    pause: "M8 5v14 M16 5v14",
    stop: "M6.5 6.5h11v11h-11z",
    lock: "M6 11h12v9H6z M8.5 11V8a3.5 3.5 0 0 1 7 0v3",
    alert: "M12 4 2.8 20h18.4L12 4Z M12 10v4.5 M12 17.3v.01",
    info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z M12 11v5 M12 7.8v.01",
    refresh: "M20 11a8 8 0 0 0-14.6-4.5L4 8 M4 4v4h4 M4 13a8 8 0 0 0 14.6 4.5L20 16 M20 20v-4h-4",
    copy: "M9 9h11v11H9z M5 15H4V4h11v1",
    sun: "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z M12 2v2 M12 20v2 M2 12h2 M20 12h2 M4.9 4.9l1.4 1.4 M17.7 17.7l1.4 1.4 M4.9 19.1l1.4-1.4 M17.7 6.3l1.4-1.4",
    moon: "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z",
    clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z M12 7v5l3 2",
    frozen: "M12 3v18 M4.2 7.5l15.6 9 M4.2 16.5l15.6-9 M9.5 4.5 12 6l2.5-1.5 M9.5 19.5 12 18l2.5 1.5",
    shield: "M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z",
    ledger: "M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z M5 17a3 3 0 0 1 3-3h11",
    code: "m8 7-5 5 5 5 M16 7l5 5-5 5",
    blocks: "M4 4h7v7H4z M13 4h7v7h-7z M4 13h7v7H4z M13 13h7v7h-7z",
    send: "M4 12 20 4l-6 16-3-7z",
    columns: "M4 5h6v14H4z M14 5h6v14h-6z",
    expand: "M4 9V4h5 M20 9V4h-5 M4 15v5h5 M20 15v5h-5",
    link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1 M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
    card: "M3 6h18v12H3z M3 10h18",
    mail: "M3 6h18v12H3z M3 7l9 6 9-6",
    calendar: "M4 6h16v14H4z M4 10h16 M8 3v4 M16 3v4",
    menu: "M4 7h16 M4 12h16 M4 17h16",
    trash: "M5 7h14 M10 7V4h4v3 M7 7l1 13h8l1-13",
    edit: "M4 20h4L19 9l-4-4L4 16z",
    download: "M12 4v11 M7 10l5 5 5-5 M5 20h14",
    eye: "M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12Z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
    history: "M3.5 12a8.5 8.5 0 1 0 2.5-6 M3 4v4h4 M12 8v4l3 2",
    wallet: "M4 7h15a1 1 0 0 1 1 1v11H4z M4 7l12-3v3 M16 13h1",
    bolt: "M13 3 5 13h6l-1 8 8-10h-6z",
    flag: "M5 21V4 M5 4h12l-2 4 2 4H5",
    check2: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z m-4-9 2.8 2.8L16 9.5",
    markets: "M4 4v16h16 M7.5 15l4-4 3 3 5-6",
    activity: "M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15z M10 20.5a2 2 0 0 0 4 0",
    faceid: "M7 3H5a2 2 0 0 0-2 2v2 M17 3h2a2 2 0 0 1 2 2v2 M7 21H5a2 2 0 0 1-2-2v-2 M17 21h2a2 2 0 0 0 2-2v-2 M9 8.5v1.5 M15 8.5v1.5 M12.2 8.5v4.2h-1.1 M8.8 15.6c1.8 1.5 4.6 1.5 6.4 0",
    key: "M14.5 14a5 5 0 1 0-4.6-3L3 17.9V21h3.1v-2.2h2.2v-2.2h2.2l1.7-1.7a5 5 0 0 0 2.3.6Z M16.5 7.5h.01",
    mic: "M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z M6 11a6 6 0 0 0 12 0 M12 17v4",
    "wifi-off": "M2 8.8a15 15 0 0 1 4.2-2.6 M10 4.8c4.4-.5 8.9 1 12 4 M5 12.6a10 10 0 0 1 3.7-2.3 M15 10.6c1.5.4 2.9 1.1 4 2.1 M8.5 16.3a5 5 0 0 1 7 0 M12 20h.01 M3 3l18 18",
    "bell-off": "M8.7 4.3A6 6 0 0 1 18 9.5V14 M6 9.4V16l-1.5 2H17 M10 20.5a2 2 0 0 0 4 0 M3 3l18 18",
    settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M19.4 13.5a7.6 7.6 0 0 0 0-3l2-1.6-2-3.4-2.4 1a7.6 7.6 0 0 0-2.6-1.5L14 2.5h-4l-.4 2.5A7.6 7.6 0 0 0 7 6.5l-2.4-1-2 3.4 2 1.6a7.6 7.6 0 0 0 0 3l-2 1.6 2 3.4 2.4-1a7.6 7.6 0 0 0 2.6 1.5l.4 2.5h4l.4-2.5a7.6 7.6 0 0 0 2.6-1.5l2.4 1 2-3.4z",
    share: "M12 15V3 M8 7l4-4 4 4 M5 12v8h14v-8",
    signout: "M15 4h4v16h-4 M10 8l-4 4 4 4 M6 12h10",
    phone: "M7 2.5h10a1 1 0 0 1 1 1v17a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1v-17a1 1 0 0 1 1-1Z M11 18.5h2",
    laptop: "M5 5h14v10H5z M3 19h18",
    star: "m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z",
    globe: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z M3 12h18 M12 3c2.5 2.6 3.7 5.6 3.7 9s-1.2 6.4-3.7 9c-2.5-2.6-3.7-5.6-3.7-9S9.5 5.6 12 3Z",
    cloud: "M7 18h10.5a4 4 0 0 0 .5-8 6 6 0 0 0-11.5-1.5A4.5 4.5 0 0 0 7 18Z",
    keyboard: "M3 6h18v12H3z M7 10h.01 M11 10h.01 M15 10h.01 M7 14h10",
    waveform: "M4 10v4 M8 7v10 M12 4v16 M16 8v8 M20 11v2",
  };
  const BOLD_ICONS = { more: 2.6 };
  function icon(name, sw) {
    const d = ICONS[name] || ICONS.info;
    const w = sw || BOLD_ICONS[name] || 1.6;
    const fill = name === "play" ? "currentColor" : "none";
    return `<svg viewBox="0 0 24 24" fill="${fill}" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${d}"/></svg>`;
  }

  const LOGO_BODY = [[6.4, 4.5, 3.2, 14], [10.8, 14.5, 3.2, 10], [15.2, 14.5, 3.2, 6], [19.6, 15, 3.2, 5.5], [24, 14.5, 3.2, 10], [28.4, 13, 2, 4.5]];
  function logoMark(size, bold) {
    const k = bold ? 1.1 : 1;
    const rect = ([x, y, w, h]) => `<rect x="${(x - (w * k - w) / 2).toFixed(2)}" y="${y}" width="${(w * k).toFixed(2)}" height="${h}" rx="0.5" fill="currentColor"/>`;
    return `<svg viewBox="0 0 32 32" width="${size}" height="${size}" fill="none" aria-hidden="true">` +
      `<path d="M8 2v20M12.4 13v16.5M25.6 13v16.5M16.8 12.5v10M21.2 13v9" stroke="currentColor" stroke-width="${bold ? 1.4 : 1.1}" stroke-linecap="round"/>` +
      `<rect x="${(2 - (3.2 * k - 3.2) / 2).toFixed(2)}" y="7" width="${(3.2 * k).toFixed(2)}" height="4" rx="0.5" style="fill:var(--acc)"/>` +
      LOGO_BODY.map(rect).join("") + "</svg>";
  }

  /* ------------------------------------------------------------ seeded data */
  function rng(seed) {
    let a = (seed >>> 0) || 1;
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function gauss(r) {
    const u = Math.max(r(), 1e-9), v = r();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
  /** Growth series starting at 1 and ending at 1 + ret. dip = [position 0..1, depth 0..1]. */
  function series(seed, n, ret, vol, dip) {
    const r = rng(seed);
    const v = [0];
    for (let i = 1; i < n; i++) v.push(v[i - 1] + gauss(r) * vol);
    if (dip) {
      const [p, depth] = dip;
      const ld = Math.log(1 - depth);
      for (let i = 0; i < n; i++) {
        const t = i / (n - 1);
        v[i] += ld * Math.exp(-Math.pow((t - p) / 0.06, 2));
      }
    }
    const end = v[n - 1];
    const tgt = Math.log(1 + ret);
    return v.map((x, i) => Math.exp(x + ((tgt - end) * i) / (n - 1)));
  }

  /* ------------------------------------------------------------ formatting */
  function fmtMoney(v) {
    const a = Math.abs(v);
    if (a >= 1e6) return "$" + (v / 1e6).toFixed(2) + "M";
    if (a >= 1e4) return "$" + (v / 1e3).toFixed(1) + "k";
    return "$" + Math.round(v).toLocaleString("en-US");
  }
  function fmtPct(v, signed) {
    const p = v * 100;
    const s = Math.abs(p) < 10 ? p.toFixed(1) : p.toFixed(0);
    return (signed && p > 0 ? "+" : "") + s + "%";
  }
  function monthLabels(from, to, count) {
    const [fy, fm] = from.split("-").map(Number);
    const [ty, tm] = to.split("-").map(Number);
    const total = (ty - fy) * 12 + (tm - fm);
    const out = [];
    for (let i = 0; i < count; i++) {
      const k = Math.round((total * i) / (count - 1));
      const m = fm - 1 + k;
      out.push(`${fy + Math.floor(m / 12)}-${String((m % 12) + 1).padStart(2, "0")}`);
    }
    return out;
  }

  /* ------------------------------------------------------------ charts */
  let gid = 0;
  const num = (v, d) => (v == null || v === "" || isNaN(+v) ? d : +v);
  const pathOf = (pts) => pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join("");
  const parseDip = (s) => (s ? s.split(":").map(Number) : null);

  function sizeOf(el) {
    if (el.dataset.h) el.style.height = el.dataset.h + "px";
    return [el.clientWidth, el.clientHeight];
  }
  function autoColor(el, ret) {
    if (el.dataset.color === "auto") el.dataset.color = ret >= 0 ? "gain" : "loss";
  }

  function drawLine(el, kind) {
    const [W, H] = sizeOf(el);
    if (!W || !H) return false;
    const d = el.dataset;
    const seed = num(d.seed, 7), ret = num(d.ret, 0.18), vol = num(d.vol, 0.012);
    const n = num(d.n, Math.max(40, Math.min(260, Math.round(W / 4))));
    const axis = d.axis || "";
    const start = num(d.start, 0);
    autoColor(el, ret);
    const padR = axis.includes("y") ? 54 : 0, padB = axis.includes("x") ? 22 : 0, padT = 6;
    const a = series(seed, n, ret, vol, parseDip(d.dip));
    const b = d.bench != null ? series(seed + 101, n, num(d.bench, 0.1), vol * 0.75) : null;
    let lo = Math.min(...a, ...(b || [])), hi = Math.max(...a, ...(b || []));
    const pad = (hi - lo) * 0.08 || 0.01;
    lo -= pad; hi += pad;
    const cw = W - padR, chH = H - padB - padT;
    const X = (i) => (i / (n - 1)) * cw;
    const Y = (v) => padT + (1 - (v - lo) / (hi - lo)) * chH;
    const id = "axg" + ++gid;
    let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><defs><linearGradient id="${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" class="ch-stop-a"/><stop offset="1" class="ch-stop-b"/></linearGradient></defs>`;
    if (axis.includes("y")) {
      for (let k = 0; k < 4; k++) {
        const v = lo + ((hi - lo) * (k + 0.5)) / 4;
        const y = Y(v);
        s += `<line class="ch-grid" x1="0" x2="${cw}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke-dasharray="1 3"/>`;
        s += `<text class="ch-lbl" x="${W}" y="${(y + 3.5).toFixed(1)}" text-anchor="end">${start ? fmtMoney(v * start) : fmtPct(v - 1, true)}</text>`;
      }
    }
    if (axis.includes("x")) {
      const labels = d.x ? d.x.split(",") : d.from && d.to ? monthLabels(d.from, d.to, 5) : [];
      labels.forEach((t, i) => {
        const x = labels.length > 1 ? (i / (labels.length - 1)) * cw : 0;
        const anchor = i === 0 ? "start" : i === labels.length - 1 ? "end" : "middle";
        s += `<text class="ch-lbl" x="${x.toFixed(1)}" y="${H - 4}" text-anchor="${anchor}">${esc(t.trim())}</text>`;
      });
    }
    const pa = a.map((v, i) => [X(i), Y(v)]);
    if (kind === "area" || d.fill != null) {
      s += `<path d="${pathOf(pa)}L${cw},${padT + chH}L0,${padT + chH}Z" fill="url(#${id})"/>`;
    }
    if (b) s += `<path class="ch-bench" d="${pathOf(b.map((v, i) => [X(i), Y(v)]))}" vector-effect="non-scaling-stroke"/>`;
    s += `<path class="ch-line" d="${pathOf(pa)}" vector-effect="non-scaling-stroke"/>`;
    if (d.marks) {
      d.marks.split(",").forEach((m) => {
        const [pos, kind] = m.trim().split(":");
        const k = Math.max(0, Math.min(n - 1, Math.round(+pos * (n - 1))));
        const [mx, my] = pa[k];
        s += `<circle class="ch-mk${kind ? " " + esc(kind) : ""}" cx="${mx.toFixed(1)}" cy="${my.toFixed(1)}" r="4"/>`;
      });
    }
    if (d.scrub != null && d.scrub !== "") {
      const k = Math.max(0, Math.min(n - 1, Math.round(num(d.scrub, 0.6) * (n - 1))));
      const [sx, sy] = pa[k];
      s += `<path class="ch-tail" d="${pathOf(pa.slice(k))}" vector-effect="non-scaling-stroke"/>`;
      s += `<line class="ch-scrub" x1="${sx.toFixed(1)}" x2="${sx.toFixed(1)}" y1="${padT}" y2="${padT + chH}"/>`;
      s += `<circle class="ch-halo" cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="9"/><circle class="ch-end" cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="4.5"/>`;
    }
    if (d.mark != null && (d.scrub == null || d.scrub === "")) {
      const [ex, ey] = pa[pa.length - 1];
      s += `<circle class="ch-halo" cx="${ex}" cy="${ey}" r="8"/><circle class="ch-end" cx="${ex}" cy="${ey}" r="3.5"/>`;
    }
    el.innerHTML = s + "</svg>";
    return true;
  }

  function drawSpark(el) {
    const [W, H] = sizeOf(el);
    if (!W || !H) return false;
    const d = el.dataset;
    const ret = num(d.ret, 0.04);
    autoColor(el, ret);
    const n = num(d.n, 32);
    const a = series(num(d.seed, 3), n, ret, num(d.vol, 0.02), parseDip(d.dip));
    const lo = Math.min(...a), hi = Math.max(...a), rr = hi - lo || 1;
    const pts = a.map((v, i) => [(i / (n - 1)) * W, 2 + (1 - (v - lo) / rr) * (H - 4)]);
    const id = "axg" + ++gid;
    let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
    if (d.fill != null) {
      s += `<defs><linearGradient id="${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" class="ch-stop-a"/><stop offset="1" class="ch-stop-b"/></linearGradient></defs>`;
      s += `<path d="${pathOf(pts)}L${W},${H}L0,${H}Z" fill="url(#${id})"/>`;
    }
    s += `<path class="ch-line" style="stroke-width:1.4" d="${pathOf(pts)}" vector-effect="non-scaling-stroke"/>`;
    el.innerHTML = s + "</svg>";
    return true;
  }

  function drawDrawdown(el) {
    const [W, H] = sizeOf(el);
    if (!W || !H) return false;
    const d = el.dataset;
    const n = num(d.n, Math.max(40, Math.min(260, Math.round(W / 4))));
    const a = series(num(d.seed, 7), n, num(d.ret, 0.18), num(d.vol, 0.012), parseDip(d.dip));
    let peak = a[0];
    const dd = a.map((v) => { peak = Math.max(peak, v); return v / peak - 1; });
    const min = Math.min(...dd) * 1.12 || -0.01;
    const axis = d.axis || "y";
    const padR = axis.includes("y") ? 54 : 0;
    const cw = W - padR;
    const X = (i) => (i / (n - 1)) * cw;
    const Y = (v) => 2 + (v / min) * (H - 4);
    let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
    s += `<line class="ch-zero" x1="0" x2="${cw}" y1="2" y2="2"/>`;
    if (padR) {
      s += `<text class="ch-lbl" x="${W}" y="10" text-anchor="end">0%</text>`;
      s += `<text class="ch-lbl" x="${W}" y="${H - 2}" text-anchor="end">${fmtPct(Math.min(...dd))}</text>`;
    }
    const pts = dd.map((v, i) => [X(i), Y(v)]);
    s += `<path class="ch-dd" d="${pathOf(pts)}L${cw},2L0,2Z" vector-effect="non-scaling-stroke"/>`;
    el.innerHTML = s + "</svg>";
    return true;
  }

  function candleData(seed, n, ret, vol) {
    const r = rng(seed + 9);
    const c = series(seed, n + 1, ret, vol);
    const out = [];
    for (let i = 1; i <= n; i++) {
      const o = c[i - 1], cl = c[i];
      const h = Math.max(o, cl) * (1 + Math.abs(gauss(r)) * vol * 0.6);
      const l = Math.min(o, cl) * (1 - Math.abs(gauss(r)) * vol * 0.6);
      out.push([o, h, l, cl]);
    }
    return out;
  }
  function candlesSvg(W, H, cs, padR, padT, padB, levels) {
    const n = cs.length;
    let lo = Infinity, hi = -Infinity;
    cs.forEach(([, h, l]) => { lo = Math.min(lo, l); hi = Math.max(hi, h); });
    const cw = W - padR, ch = H - padT - padB;
    const step = cw / n, bw = Math.max(1.5, step * 0.56);
    const Y = (v) => padT + (1 - (v - lo) / (hi - lo)) * ch;
    let s = "";
    if (levels) s += levels;
    cs.forEach(([o, h, l, c], i) => {
      const x = i * step + step / 2;
      const up = c >= o;
      const y1 = Y(Math.max(o, c)), y2 = Y(Math.min(o, c));
      s += `<line class="ch-wick" x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${Y(h).toFixed(1)}" y2="${Y(l).toFixed(1)}" stroke-width="1"/>`;
      s += `<rect class="${up ? "ch-c-up" : "ch-c-dn"}" x="${(x - bw / 2).toFixed(1)}" y="${y1.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, y2 - y1).toFixed(1)}" stroke-width="1"/>`;
    });
    return { s, Y, lo, hi };
  }

  function drawCandles(el) {
    const [W, H] = sizeOf(el);
    if (!W || !H) return false;
    const d = el.dataset;
    const n = num(d.n, Math.max(20, Math.round(W / 9)));
    const cs = candleData(num(d.seed, 11), n, num(d.ret, 0.06), num(d.vol, 0.014));
    const axis = d.axis || "";
    const padR = axis.includes("y") ? 54 : 0;
    const base = num(d.base, 0);
    const res = candlesSvg(W, H, cs, padR, 6, 6);
    let s = `<svg viewBox="0 0 ${W} ${H}">` + res.s;
    if (padR) {
      for (let k = 0; k < 4; k++) {
        const v = res.lo + ((res.hi - res.lo) * (k + 0.5)) / 4;
        const y = res.Y(v);
        s += `<text class="ch-lbl" x="${W}" y="${(y + 3.5).toFixed(1)}" text-anchor="end">${base ? (v * base).toFixed(2) : fmtPct(v - 1, true)}</text>`;
      }
    }
    el.innerHTML = s + "</svg>";
    return true;
  }

  function drawBars(el) {
    const [W, H] = sizeOf(el);
    if (!W || !H) return false;
    const d = el.dataset;
    let vals;
    if (d.values) vals = d.values.split(",").map(Number);
    else {
      const r = rng(num(d.seed, 5));
      vals = Array.from({ length: num(d.n, 30) }, () => gauss(r) + num(d.mean, 0.15));
    }
    const m = Math.max(...vals.map(Math.abs)) || 1;
    const hasNeg = vals.some((v) => v < 0);
    const zero = hasNeg ? H / 2 : H - 1;
    const scale = hasNeg ? H / 2 - 2 : H - 3;
    const step = W / vals.length, bw = Math.max(1.5, step * 0.62);
    let s = `<svg viewBox="0 0 ${W} ${H}"><line class="ch-zero" x1="0" x2="${W}" y1="${zero}" y2="${zero}"/>`;
    vals.forEach((v, i) => {
      const h = (Math.abs(v) / m) * scale;
      const x = i * step + (step - bw) / 2;
      s += `<rect class="${v >= 0 ? "ch-bar-g" : "ch-bar-l"}" x="${x.toFixed(1)}" y="${(v >= 0 ? zero - h : zero).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, h).toFixed(1)}" rx="1"/>`;
    });
    el.innerHTML = s + "</svg>";
    return true;
  }

  function drawHeat(el) {
    const d = el.dataset;
    const [y0, y1] = (d.years || "2021-2025").split("-").map(Number);
    const upto = num(d.upto, 10);
    const r = rng(num(d.seed, 21));
    const mean = num(d.mean, 0.8), sd = num(d.sd, 2.6);
    const rows = [];
    let max = 0;
    for (let y = y0; y <= y1; y++) {
      const ms = [];
      for (let m = 0; m < 12; m++) {
        if (y === y1 && m >= upto) { ms.push(null); continue; }
        const v = gauss(r) * sd + mean;
        max = Math.max(max, Math.abs(v));
        ms.push(v);
      }
      rows.push([y, ms]);
    }
    const H = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
    let s = `<span class="hd"></span>` + H.map((h) => `<span class="hd">${h}</span>`).join("") + `<span class="hd tot">Year</span>`;
    rows.forEach(([y, ms]) => {
      s += `<span class="yr">${y}</span>`;
      let tot = 1;
      ms.forEach((v) => {
        if (v == null) { s += `<span class="na">·</span>`; return; }
        tot *= 1 + v / 100;
        const k = Math.round(12 + (Math.abs(v) / max) * 50);
        const c = v >= 0 ? "var(--gain)" : "var(--loss)";
        s += `<span style="background:color-mix(in srgb, ${c} ${k}%, transparent);color:${k > 40 ? "var(--fg)" : "var(--fg-2)"}">${v > 0 ? "+" : ""}${v.toFixed(1)}</span>`;
      });
      const t = (tot - 1) * 100;
      s += `<span class="tot ${t >= 0 ? "gain" : "loss"}">${t > 0 ? "+" : ""}${t.toFixed(1)}%</span>`;
    });
    el.classList.add("heat");
    el.innerHTML = s;
    return true;
  }

  const PALETTE = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)"];
  function drawAlloc(el) {
    const items = (el.dataset.items || "").split(",").filter(Boolean).map((p, i) => {
      const [k, v] = p.split(":");
      const sym = k.trim();
      return { k: sym, v: +v, c: /^cash$/i.test(sym) ? "var(--c5)" : PALETTE[i % PALETTE.length] };
    });
    let s = `<div class="alloc-bar">` + items.map((it) => `<i style="width:${it.v}%;background:${it.c}"></i>`).join("") + `</div>`;
    if (el.dataset.legend !== "none") {
      s += `<div class="alloc-legend">` + items.map((it) => `<span style="--sw:${it.c}"><b>${esc(it.k)}</b>${it.v.toFixed(1)}%</span>`).join("") + `</div>`;
    }
    el.innerHTML = s;
    return true;
  }

  function drawArt(el) {
    const W = el.clientWidth, H = el.clientHeight;
    if (!W || !H) return false;
    const d = el.dataset;
    const kind = d.art || "candles";
    const seed = num(d.seed, 4242);
    const base = num(d.base, 612.5);
    const lvls = [0.3, 0.62];
    let lv = "";
    lvls.forEach((p, i) => {
      const y = (H * p).toFixed(1);
      lv += `<line class="ch-lvl" x1="0" x2="${W}" y1="${y}" y2="${y}"/>`;
      lv += `<text class="ch-lvl-t" x="${W - 12}" y="${(+y - 6).toFixed(1)}" text-anchor="end">${(base * (1 + (lvls.length - i) * 0.012)).toFixed(2)}</text>`;
    });
    let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
    if (kind === "line" || kind === "equity") {
      const n = Math.round(W / 6);
      const a = series(seed, n, num(d.ret, 0.5), 0.02);
      const lo = Math.min(...a), hi = Math.max(...a);
      const pts = a.map((v, i) => [(i / (n - 1)) * W, H * 0.12 + (1 - (v - lo) / (hi - lo)) * H * 0.7]);
      s += lv + `<path class="ch-line" d="${pathOf(pts)}"/>`;
    } else {
      const n = Math.round(W / 12);
      const cs = candleData(seed, n, num(d.ret, 0.4), 0.02);
      s += candlesSvg(W, H, cs, 0, H * 0.1, H * 0.22, lv).s;
    }
    el.innerHTML = s + "</svg>";
    return true;
  }

  /* ------------------------------------------------------------ page art
     The site's background chart (sectionArt.ts: chartArt and SECTION_SHAPES), one market shape per
     area, drawn behind the top of a screen from [data-page-art="<shape>"]. */
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const r1 = (v) => Math.round(v * 10) / 10;
  const PAGE_SHAPES = {
    top: { kind: "candles", seed: 4242, path: (t) => 0.22 + t * 0.66 + Math.sin(t * 14) * 0.03 + Math.sin(t * 5.7) * 0.04, levels: [0.78, 0.5], base: 612.5 },
    build: { kind: "candles", seed: 5101, path: (t) => 0.5 + Math.sin(t * 8) * 0.26 + Math.sin(t * 21) * 0.07, levels: [0.66, 0.34], base: 418.2 },
    backtest: { kind: "candles", seed: 6203, path: (t) => 0.2 + t * 0.62 + Math.sin(t * 13) * 0.05 - (t > 0.42 && t < 0.58 ? Math.sin(((t - 0.42) / 0.16) * Math.PI) * 0.16 : 0), levels: [0.75, 0.45], base: 25000 },
    copilot: { kind: "candles", seed: 7307, path: (t) => 0.85 - 3.1 * t * (1 - t) + t * 0.05 + Math.sin(t * 17) * 0.03, levels: [0.25], base: 182.4 },
    live: { kind: "candles", seed: 8411, path: (t) => 0.3 + t * 0.45 + Math.sin(t * 11) * 0.06, levels: [0.75, 0.45], base: 103410 },
    own: { kind: "candles", seed: 9513, path: (t) => 0.12 + t * 0.72 + Math.sin(t * 7) * 0.09, levels: [0.72, 0.48], base: 612.5, sparse: true },
    join: { kind: "candles", seed: 1619, path: (t) => 0.12 + Math.pow(t, 1.5) * 0.78 + Math.sin(t * 15) * 0.03, levels: [0.75, 0.45], base: 682.15 },
  };
  /** Which shape each area uses, like the site's one shape per section. */
  const AREA_SHAPES = { onboarding: "top", checkin: "live", alerts: "own", glance: "backtest", markets: "build", copilot: "copilot", edge: "join" };
  let artGrad = 0;

  function drawPageArt(el) {
    const W = el.clientWidth, H = el.clientHeight;
    if (!W || !H) return false;
    const d = el.dataset;
    const shape = PAGE_SHAPES[d.pageArt] || PAGE_SHAPES[AREA_SHAPES[d.pageArt]] || PAGE_SHAPES.top;
    const top = H * num(d.top, 0.12);
    const ht = d.band ? H * num(d.band, 0.5) : Math.min(H * 0.5, 420);
    const r = rng(shape.seed + num(d.seed, 0));
    const y = (v) => top + (1 - v) * ht;
    const val = (t) => clamp(shape.path(t), 0.04, 0.96);
    let body = "", acc = "", lv = "";
    const rect = (x, yy, w, h, cls, op) => `<rect x="${r1(x)}" y="${r1(yy)}" width="${r1(w)}" height="${r1(h)}"${cls ? ` class="${cls}"` : ""}${op != null ? ` fill-opacity="${op}"` : ""}/>`;
    const line = (x1, y1, x2, y2, extra) => `<line x1="${r1(x1)}" y1="${r1(y1)}" x2="${r1(x2)}" y2="${r1(y2)}"${extra || ""}/>`;

    if (shape.kind === "candles") {
      const n = Math.max(24, Math.min(80, Math.floor(W / (shape.sparse ? 13 : 10))));
      const sp = W / n;
      const bw = Math.max(2, sp * (shape.sparse ? 0.42 : 0.55));
      const closes = [];
      let prev = val(0), vol = "";
      for (let i = 0; i < n; i++) {
        const open = prev;
        const close = clamp(val((i + 1) / n) + (r() - 0.5) * 0.06, 0.03, 0.97);
        const high = Math.min(0.99, Math.max(open, close) + r() * 0.035);
        const low = Math.max(0.01, Math.min(open, close) - r() * 0.035);
        const cx = i * sp + sp / 2;
        const t0 = y(Math.max(open, close)), b0 = y(Math.min(open, close));
        body += line(cx, y(high), cx, y(low));
        body += rect(cx - bw / 2, t0, bw, Math.max(1.5, b0 - t0), close >= open ? "ho" : "so");
        const vh = 5 + r() * 26 * (0.5 + Math.abs(close - open) * 8);
        vol += rect(cx - bw / 2, top + ht + 52 - vh, bw, vh, "ti", 0.6);
        closes.push([cx, close]);
        prev = close;
      }
      body += vol;
      const ma = closes.map(([cx], i) => {
        const win = closes.slice(Math.max(0, i - 8), i + 1);
        const avg = win.reduce((s, c) => s + c[1], 0) / win.length;
        return `${i ? "L" : "M"}${r1(cx)},${r1(y(avg))}`;
      }).join("");
      acc += `<path d="${ma}" stroke-width="1.6"/>`;
    } else {
      const steps = 120, pts = [];
      for (let i = 0; i <= steps; i++) {
        const t = i / steps;
        pts.push([t * W, clamp(val(t) + (r() - 0.5) * 0.02, 0.03, 0.97)]);
      }
      const ln = pts.map(([x, v], i) => `${i ? "L" : "M"}${r1(x)},${r1(y(v))}`).join("");
      if (shape.kind === "steps") {
        let held = pts[0][1], dd = `M0,${r1(y(held))}`;
        const marks = [];
        pts.forEach(([x, v], i) => {
          if (i > 0 && i % 12 === 0 && v !== held) { dd += ` H${r1(x)} V${r1(y(v))}`; marks.push(x); held = v; }
        });
        dd += ` H${r1(W)}`;
        acc += `<path d="${dd}" stroke-width="1.6"/>`;
        const b = top + ht + 22;
        marks.forEach((x) => { body += line(x, b - 6, x, b + 6); });
        body += line(0, b, W, b, ` stroke-width="0.6"`);
        body += `<path d="${ln}" stroke-dasharray="2 3"/>`;
      } else {
        const gid = "pa-g" + ++artGrad;
        acc += `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="currentColor" stop-opacity="0.5"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>`;
        acc += `<path d="${ln} L${r1(W)},${r1(top + ht)} L0,${r1(top + ht)} Z" fill="url(#${gid})" stroke="none"/>`;
        acc += `<path d="${ln}" stroke-width="1.6"/>`;
        if (shape.kind === "equity") {
          const b = top + ht + 26;
          let peak = 0, dd = `M0,${r1(b)}`;
          pts.forEach(([x, v]) => { peak = Math.max(peak, v); dd += ` L${r1(x)},${r1(b + (peak - v) * 200)}`; });
          body += line(0, b, W, b) + `<path d="${dd} L${r1(W)},${r1(b)} Z" class="ti" fill-opacity="0.45"/>`;
        } else {
          const bars = Math.floor(W / 9);
          for (let i = 0; i < bars; i++) {
            const bh = 5 + r() * 24 * (0.4 + i / bars);
            body += rect(i * 9, top + ht + 56 - bh, 5, bh, "ti", 1);
          }
        }
      }
    }
    shape.levels.forEach((v) => {
      const yy = y(v);
      const p = shape.base * (1 + (v - 0.5) * 0.06);
      const label = shape.base >= 10000 ? "$" + Math.round(p).toLocaleString("en-US") : p.toFixed(2);
      lv += line(0, yy, W - 58, yy, ` stroke-dasharray="2 4"`);
      lv += `<text x="${r1(W - 8)}" y="${r1(yy + 3.5)}" text-anchor="end">${label}</text>`;
    });
    el.innerHTML =
      `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">` +
      `<g class="sa sabody">${body}</g><g class="sa">${lv}</g><g class="sa acc">${acc}</g></svg>`;
    return true;
  }

  const DRAW = { line: (el) => drawLine(el, "line"), area: (el) => drawLine(el, "area"), spark: drawSpark, drawdown: drawDrawdown, candles: drawCandles, bars: drawBars, heat: drawHeat, alloc: drawAlloc };

  /* ------------------------------------------------------------ fillers */
  const SB_ICONS =
    `<span class="r">` +
    `<svg width="18" height="11" viewBox="0 0 18 11" fill="currentColor"><rect x="0" y="7" width="3" height="4" rx="0.8"/><rect x="5" y="5" width="3" height="6" rx="0.8"/><rect x="10" y="2.5" width="3" height="8.5" rx="0.8"/><rect x="15" y="0" width="3" height="11" rx="0.8"/></svg>` +
    `<svg width="16" height="11" viewBox="0 0 16 11" fill="currentColor"><path d="M8 2.2c2.3 0 4.4.9 6 2.4l1.1-1.2A10.3 10.3 0 0 0 8 .6 10.3 10.3 0 0 0 .9 3.4L2 4.6a8.6 8.6 0 0 1 6-2.4Zm0 3.3c1.4 0 2.6.5 3.6 1.4l1.1-1.2A6.9 6.9 0 0 0 8 3.9a6.9 6.9 0 0 0-4.7 1.8l1.1 1.2c1-.9 2.2-1.4 3.6-1.4Zm0 3.2c.5 0 1 .2 1.3.5L8 10.6 6.7 9.2c.3-.3.8-.5 1.3-.5Z"/></svg>` +
    `<svg width="27" height="13" viewBox="0 0 27 13" fill="none"><rect x="0.5" y="0.5" width="23" height="12" rx="3.5" stroke="currentColor" opacity="0.4"/><rect x="2" y="2" width="18" height="9" rx="2" fill="currentColor"/><path d="M25 4.5v4c.8-.3 1.3-1.1 1.3-2s-.5-1.7-1.3-2Z" fill="currentColor" opacity="0.45"/></svg>` +
    `</span>`;
  /** iOS status bar markup. kind: "lock" leaves the time out (the clock is on the screen), "ipad" adds the date. */
  function statusBar(kind, time) {
    const t = time || "10:42";
    if (kind === "lock") return `<span class="cr"></span>` + SB_ICONS;
    if (kind === "ipad") return `<span>${esc(t)}<span class="dt">Tue Nov 17</span></span>` + SB_ICONS;
    return `<span>${esc(t)}</span>` + SB_ICONS;
  }

  const TAB_LABELS = { home: "Home", strategies: "Strategies", portfolio: "Portfolio", copilot: "Copilot", account: "Account", backtests: "Backtests", sessions: "Sessions", markets: "Markets", activity: "Activity", bell: "Alerts", search: "Search" };

  function fill(root) {
    root.querySelectorAll("[data-logo]:not([data-ax-done])").forEach((el) => {
      const size = num(el.dataset.size, 28);
      const markOnly = el.dataset.logo === "mark";
      el.classList.add("logo");
      el.innerHTML = logoMark(size, size >= 24) + (markOnly ? "" : `<span class="word">LlamaTrade</span>`);
      el.dataset.axDone = "1";
    });
    root.querySelectorAll("[data-icon]:not([data-ax-done])").forEach((el) => {
      el.classList.add("ic");
      el.innerHTML = icon(el.dataset.icon);
      el.dataset.axDone = "1";
    });
    root.querySelectorAll("[data-tabs]:not([data-ax-done])").forEach((el) => {
      const items = (el.dataset.items || "home,sessions,markets,activity,account").split(",").map((s) => s.trim());
      el.classList.add("m-tabs");
      el.style.setProperty("--n", items.length);
      const dots = (el.dataset.dot || "").split(",").map((x) => x.trim());
      el.innerHTML = items.map((k) => `<a class="${k === el.dataset.tabs ? "on" : ""}${dots.includes(k) ? " rd" : ""}"><span class="ic">${icon(ICONS[k] ? k : "info")}</span>${esc(TAB_LABELS[k] || k)}</a>`).join("");
      el.dataset.axDone = "1";
    });
    root.querySelectorAll("[data-appicon]:not([data-ax-done])").forEach((el) => {
      el.classList.add("io-ai");
      el.innerHTML = logoMark(64, true);
      el.dataset.axDone = "1";
    });
    root.querySelectorAll("[data-kb]:not([data-ax-done])").forEach((el) => {
      const rows = ["qwertyuiop", "asdfghjkl", "zxcvbnm"];
      const key = (c, cls) => `<span class="k${cls ? " " + cls : ""}">${c}</span>`;
      el.classList.add("io-kb");
      el.innerHTML =
        (el.dataset.kb ? `<div class="sug">${el.dataset.kb.split("|").map((w) => `<span>${esc(w)}</span>`).join("")}</div>` : "") +
        `<div class="kr">${[...rows[0]].map((c) => key(c)).join("")}</div>` +
        `<div class="kr in">${[...rows[1]].map((c) => key(c)).join("")}</div>` +
        `<div class="kr">${key("&#8679;", "fn w")}${[...rows[2]].map((c) => key(c)).join("")}${key("&#9003;", "fn w")}</div>` +
        `<div class="kr">${key("123", "fn w2")}${key("space", "sp")}${key("send", "fn w2 go")}</div>` +
        `<div class="kb-foot"><span class="ic">${icon("globe")}</span><span class="ic">${icon("mic")}</span></div>`;
      el.dataset.axDone = "1";
    });
    root.querySelectorAll("[data-wave]:not([data-ax-done])").forEach((el) => {
      const r = rng(num(el.dataset.wave, 5));
      const n = num(el.dataset.n, 36);
      el.classList.add("io-wave");
      el.innerHTML = Array.from({ length: n }, (_, i) => {
        const env = Math.sin((Math.PI * (i + 0.5)) / n);
        return `<i style="height:${Math.round(8 + env * (10 + r() * 42))}%"></i>`;
      }).join("");
      el.dataset.axDone = "1";
    });
  }

  /** Draws every pending chart and art layer inside root. Hidden ones are retried when shown. */
  function render(root) {
    root = root || document;
    fill(root);
    root.querySelectorAll("[data-chart]:not([data-ax-done])").forEach((el) => {
      const f = DRAW[el.dataset.chart];
      if (f && f(el)) el.dataset.axDone = "1";
    });
    root.querySelectorAll("[data-art]:not([data-ax-done])").forEach((el) => {
      el.classList.add("art");
      if (drawArt(el)) el.dataset.axDone = "1";
    });
    root.querySelectorAll(".ax-phone-scr").forEach((scr, i) => {
      if (scr.querySelector("[data-page-art], .page-art, .io-lock")) return;
      const sf = scr.closest("[data-surface]");
      const area = sf ? sf.dataset.surface.split("/")[0] : "top";
      scr.insertAdjacentHTML("afterbegin", `<div data-page-art="${area}" data-seed="${i * 7}" data-top="0.06" data-band="0.6" style="--pa-h:360px;--pa-solid:30%"></div>`);
    });
    root.querySelectorAll("[data-page-art]:not([data-ax-done])").forEach((el) => {
      el.classList.add("page-art");
      el.setAttribute("aria-hidden", "true");
      if (drawPageArt(el)) el.dataset.axDone = "1";
    });
  }

  /* ------------------------------------------------------------ viewer */
  const PAGES = [
    ["index.html", "Overview"],
    ["area-onboarding.html", "Onboarding"],
    ["area-checkin.html", "Check-in"],
    ["area-alerts.html", "Alerts"],
    ["area-glance.html", "Glance"],
    ["area-markets-mobile.html", "Markets"],
    ["area-copilot-mobile.html", "Copilot"],
    ["area-edge.html", "Edge cases"],
  ];
  /** Natural sizes of each device frame, bezel included. */
  const NAT = { phone: [412, 866], tablet: [1214, 854], watch: [236, 288] };
  const PK = "axm-picks", PKM = "axm-picks-meta";
  const pageFile = decodeURIComponent(location.pathname.split("/").pop() || "index.html");
  let surfaces = [];
  let current = 0;

  const picks = () => store.get(PK, {});
  const metas = () => store.get(PKM, {});

  let toastTimer = 0;
  function toast(msg) {
    let t = document.querySelector(".ax-toast");
    if (!t) { t = document.createElement("div"); t.className = "ax-toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
    t.textContent = msg;
    t.classList.add("on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("on"), 1800);
  }

  function buildTop() {
    const top = document.createElement("header");
    top.className = "ax-top";
    const links = PAGES.map(([href, label]) => `<a href="${href}" class="${href === pageFile ? "on" : ""}${href === "index.html" ? " ov" : ""}">${label}</a>`).join("");
    top.innerHTML =
      `<div class="ax-wrap">` +
      `<a class="ax-brand" href="index.html" aria-label="LlamaTrade mobile explorations">${logoMark(52, true)}<span class="word">LlamaTrade</span><span class="ttl">Mobile explorations</span></a>` +
      `<nav class="ax-links" aria-label="Areas">${links}</nav>` +
      `<div class="ax-modes ax-seg" role="group" aria-label="Colour mode"><button data-mode="light">Light</button><button data-mode="dark">Dark</button></div>` +
      `</div>`;
    document.body.prepend(top);
    top.querySelectorAll(".ax-modes button").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode, true)));
    setMode(currentMode(), false);
    const on = top.querySelector(".ax-links a.on");
    if (on) on.scrollIntoView({ block: "nearest", inline: "center" });
  }

  function buildIntro(main) {
    if (document.querySelector(".ax-intro") || !surfaces.length) return;
    const title = document.body.dataset.title || document.title || "Explorations";
    const desc = document.body.dataset.desc || "";
    const intro = document.createElement("header");
    intro.className = "ax-intro";
    intro.innerHTML =
      `<div class="art" data-art="candles" data-seed="${title.length * 97 + 11}"></div><div class="glow"></div>` +
      `<div class="ax-wrap"><div class="ax-kick over"><span class="a">Mobile explorations</span><span>${surfaces.length} ${surfaces.length === 1 ? "surface" : "surfaces"}</span><span class="ax-intro-cnt"></span></div>` +
      `<h1>${esc(title)}</h1>${desc ? `<p class="lede">${esc(desc)}</p>` : ""}<nav class="ax-index"></nav></div>`;
    main.before(intro);
  }

  function frameKind(f) { return NAT[f.dataset.frame] ? f.dataset.frame : "phone"; }
  function frameNat(f) { return NAT[frameKind(f)]; }

  function buildFrame(f, sec) {
    if (f.classList.contains("ax-frame")) return;
    const kind = frameKind(f);
    const scr = document.createElement("div");
    while (f.firstChild) scr.appendChild(f.firstChild);
    const dev = deviceShell(kind, f.dataset, scr);
    f.appendChild(dev);
    f.classList.add("ax-frame", "ax-frame-p", "ax-frame-" + kind);
    const cap = f.dataset.caption != null ? f.dataset.caption : kind === "tablet" ? "iPad · 1180" : kind === "watch" ? "Watch" : "iPhone · 390";
    if (cap) {
      const c = document.createElement("div");
      c.className = "ax-cap";
      c.textContent = cap;
      f.appendChild(c);
      f.classList.add("has-cap");
    }
    const z = document.createElement("button");
    z.className = "ax-zbtn";
    z.type = "button";
    z.title = "View larger";
    z.setAttribute("aria-label", "View larger");
    z.innerHTML = icon("expand", 1.8);
    z.addEventListener("click", (e) => { e.stopPropagation(); openZoom(f, sec); });
    f.appendChild(z);
  }

  /** Wraps screen content in a device: status bar, island, home indicator. Shared with app.html. */
  function deviceShell(kind, ds, scr) {
    const dev = document.createElement("div");
    dev.className = "ax-dev ax-" + kind + (ds.island === "none" ? " no-island" : "");
    scr.classList.add("ax-phone-scr");
    if (kind === "tablet") scr.classList.add("ax-tablet-scr");
    if (kind === "watch") scr.classList.add("ax-watch-scr");
    const sbKind = ds.statusbar || "";
    if (kind !== "watch" && sbKind !== "none") {
      const sb = document.createElement("div");
      sb.className = "sb" + (sbKind === "lock" || sbKind === "light" ? " on-wall" : "") + (kind === "tablet" ? " ipad" : "");
      sb.innerHTML = statusBar(kind === "tablet" ? "ipad" : sbKind, ds.time);
      scr.prepend(sb);
    }
    if (kind !== "watch") {
      const hi = document.createElement("i");
      hi.className = "hi" + (sbKind === "lock" || sbKind === "light" ? " on-wall" : "");
      scr.appendChild(hi);
    }
    dev.appendChild(scr);
    return dev;
  }
  function deviceHTML(kind, ds, html) {
    const scr = document.createElement("div");
    scr.innerHTML = html;
    return deviceShell(kind, ds, scr).outerHTML;
  }

  function sizeFrame(f, s) {
    const [w, h] = frameNat(f);
    f.style.width = (w * s).toFixed(1) + "px";
    f.style.height = (h * s).toFixed(1) + "px";
    f.querySelector(":scope > .ax-dev").style.transform = `scale(${s.toFixed(4)})`;
  }

  /** One shared scale for every device in the option, so a watch stays watch-sized beside a phone. */
  function layoutOpt(sec, opt) {
    const pair = opt.querySelector(":scope > .ax-pair");
    if (!pair) return;
    const cs = getComputedStyle(pair);
    const W = pair.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    if (W <= 0) return;
    const cmp = sec.classList.contains("is-compare");
    const F = [...pair.querySelectorAll(":scope > .ax-phones > [data-frame]")];
    if (!F.length) return;
    const pg = cmp ? 14 : 34;
    const sumW = F.reduce((n, f) => n + frameNat(f)[0], 0);
    const hasTab = F.some((f) => frameKind(f) === "tablet");
    const cap = hasTab ? (cmp ? 0.5 : 1) : (cmp ? 300 : 360) / NAT.phone[0];
    const s = Math.min(cap, (W - (F.length - 1) * pg) / sumW);
    pair.classList.add("ax-stack");
    F.forEach((f) => sizeFrame(f, s));
  }

  function layoutSurface(sec) {
    const vis = sec.classList.contains("is-compare") ? sec._opts : sec._opts.filter((o) => o.classList.contains("on"));
    vis.forEach((o) => { layoutOpt(sec, o); render(o); });
  }

  function setupSurface(sec, idx) {
    const opts = [...sec.querySelectorAll(":scope > .ax-opt")];
    sec._opts = opts;
    const sid = sec.dataset.surface || sec.id || "surface-" + (idx + 1);
    sec.dataset.surface = sid;
    if (!sec.id) sec.id = sid.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
    sec.dataset.cmpf = "both";
    const title = sec.dataset.title || sid;

    const head = document.createElement("header");
    head.className = "ax-sh";
    head.innerHTML =
      `<div class="ax-kick"><span class="a">${esc(sec.dataset.area || "")}</span><span>${String(idx + 1).padStart(2, "0")} / ${String(surfaces.length).padStart(2, "0")}</span><span class="pk"></span></div>` +
      `<h2>${esc(title)}</h2>` + (sec.dataset.why ? `<p class="why">${esc(sec.dataset.why)}</p>` : "");

    const bar = document.createElement("div");
    bar.className = "ax-bar";
    const tabs = opts.map((o, i) => {
      const id = o.dataset.opt || String.fromCharCode(65 + i);
      o.dataset.opt = id;
      return `<button class="ax-tab${o.hasAttribute("data-rec") ? " rec" : ""}" role="tab" data-opt="${esc(id)}"><span class="L">${esc(id)}</span><span>${esc(o.dataset.name || "Option " + id)}</span>${o.hasAttribute("data-rec") ? '<i class="rcm">Rec</i>' : ""}<i class="pkd" title="Picked"></i></button>`;
    }).join("");
    bar.innerHTML =
      `<div class="ax-tabs" role="tablist" aria-label="Options">${tabs}</div>` +
      `<div class="ax-act">` +
      `<button class="ax-btn ax-cmp" type="button">${icon("columns", 1.7)}Compare <kbd>C</kbd></button>` +
      `<button class="ax-btn pri ax-pick" type="button"></button>` +
      `</div>`;

    const note = document.createElement("p");
    note.className = "ax-note";

    const wrap = document.createElement("div");
    wrap.className = "ax-opts";
    opts.forEach((o) => {
      const frames = [...o.querySelectorAll(":scope > [data-frame]")];
      const pair = document.createElement("div");
      pair.className = "ax-pair";
      const phones = document.createElement("div");
      phones.className = "ax-phones";
      frames.forEach((f) => {
        buildFrame(f, sec);
        phones.appendChild(f);
      });
      if (phones.children.length) pair.appendChild(phones);
      const colh = document.createElement("div");
      colh.className = "ax-colh";
      colh.innerHTML =
        `<button class="L" type="button" title="Show this option">${esc(o.dataset.opt)}</button>` +
        `<div class="nm">${esc(o.dataset.name || "")}</div>` +
        `<button class="ax-btn sm ax-cpick" type="button">Pick</button>` +
        (o.dataset.note ? `<p class="nt">${esc(o.dataset.note)}</p>` : "");
      o.prepend(colh);
      o.appendChild(pair);
      colh.querySelector(".L").addEventListener("click", () => setActive(sec, o.dataset.opt, true));
      colh.querySelector(".ax-cpick").addEventListener("click", () => { setActive(sec, o.dataset.opt, false); pick(sec, o.dataset.opt); });
      wrap.appendChild(o);
    });

    sec.prepend(head, bar, note, wrap);
    bar.querySelectorAll(".ax-tab").forEach((b) => b.addEventListener("click", () => setActive(sec, b.dataset.opt, true)));
    bar.querySelector(".ax-cmp").addEventListener("click", () => toggleCompare(sec));
    bar.querySelector(".ax-pick").addEventListener("click", () => pick(sec, sec._active));

    const picked = picks()[sid];
    sec._active = opts.some((o) => o.dataset.opt === picked) ? picked : opts[0] && opts[0].dataset.opt;
    if (window.ResizeObserver) {
      let raf = 0;
      new ResizeObserver(() => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => layoutSurface(sec)); }).observe(wrap);
    }
  }

  function optOf(sec, id) { return sec._opts.find((o) => o.dataset.opt === id); }

  function setActive(sec, id, user) {
    if (!optOf(sec, id)) return;
    sec._active = id;
    refreshSurface(sec);
    layoutSurface(sec);
    if (user) {
      try { history.replaceState(null, "", "#" + sec.id + ":" + id); } catch (e) { /* file url */ }
    }
  }

  function toggleCompare(sec, force) {
    const on = force != null ? force : !sec.classList.contains("is-compare");
    sec.classList.toggle("is-compare", on);
    refreshSurface(sec);
    requestAnimationFrame(() => layoutSurface(sec));
  }

  function pick(sec, id) {
    const o = optOf(sec, id);
    if (!o) return;
    const sid = sec.dataset.surface;
    const p = picks(), m = metas();
    const title = sec.dataset.title || sid;
    if (p[sid] === id) {
      delete p[sid];
      delete m[sid];
      toast(`Pick cleared for ${title}`);
    } else {
      p[sid] = id;
      m[sid] = {
        title,
        area: sec.dataset.area || "",
        option: o.dataset.name || id,
        optionId: id,
        note: o.dataset.note || "",
        page: pageFile,
        anchor: sec.id,
        at: new Date().toISOString(),
      };
      toast(`Picked ${id}, ${o.dataset.name || ""}`);
    }
    store.set(PK, p);
    store.set(PKM, m);
    refreshAll();
    document.dispatchEvent(new CustomEvent("ax:pick", { detail: { surface: sid, option: p[sid] || null } }));
  }

  function refreshSurface(sec) {
    const p = picks()[sec.dataset.surface];
    const act = sec._active;
    const cmp = sec.classList.contains("is-compare");
    sec.querySelectorAll(".ax-tab").forEach((b) => {
      b.classList.toggle("on", b.dataset.opt === act);
      b.classList.toggle("picked", b.dataset.opt === p);
      b.setAttribute("aria-selected", b.dataset.opt === act ? "true" : "false");
    });
    sec._opts.forEach((o) => {
      o.classList.toggle("on", o.dataset.opt === act);
      o.classList.toggle("picked", o.dataset.opt === p);
      const cp = o.querySelector(".ax-cpick");
      if (cp) {
        cp.classList.toggle("picked", o.dataset.opt === p);
        cp.innerHTML = o.dataset.opt === p ? icon("check", 2) + "Picked" : "Pick";
      }
    });
    const o = optOf(sec, act);
    const note = sec.querySelector(":scope > .ax-note");
    if (o && note) note.innerHTML = (o.dataset.name ? `<b>${esc(act)}. ${esc(o.dataset.name)}.</b> ` : "") + esc(o.dataset.note || "");
    const pb = sec.querySelector(".ax-pick");
    if (pb) {
      const isP = p === act;
      pb.classList.toggle("pri", !isP);
      pb.classList.toggle("picked", isP);
      pb.innerHTML = isP ? `${icon("check", 2)}Picked ${esc(act)} <kbd>P</kbd>` : `Pick ${esc(act)} <kbd>P</kbd>`;
    }
    const cb = sec.querySelector(".ax-cmp");
    if (cb) {
      cb.classList.toggle("is-on", cmp);
      cb.innerHTML = `${icon(cmp ? "x" : "columns", 1.7)}${cmp ? "Close compare" : "Compare"} <kbd>C</kbd>`;
    }
    const pk = sec.querySelector(".ax-sh .pk");
    if (pk) {
      const po = p && optOf(sec, p);
      pk.textContent = po ? `Picked ${p}, ${po.dataset.name || ""}` : "";
    }
  }

  function refreshAll() {
    surfaces.forEach(refreshSurface);
    const p = picks();
    const done = surfaces.filter((s) => p[s.dataset.surface]).length;
    const idx = document.querySelector(".ax-index");
    if (idx) {
      idx.innerHTML = surfaces.map((s, i) => {
        const v = p[s.dataset.surface];
        return `<a href="#${s.id}" class="${v ? "done" : ""}"><i>${String(i + 1).padStart(2, "0")}</i>${esc(s.dataset.title || s.id)}<b>${v ? esc(v) : "·"}</b></a>`;
      }).join("");
    }
    const ic = document.querySelector(".ax-intro-cnt");
    if (ic) ic.textContent = `${done} decided`;
    const dock = document.querySelector(".ax-dock");
    if (dock) {
      dock.querySelector(".cnt b").textContent = `${done} of ${surfaces.length}`;
      dock.querySelector(".bar i").style.width = surfaces.length ? (done / surfaces.length) * 100 + "%" : "0";
      const nx = dock.querySelector("[data-ax='next']");
      nx.innerHTML = done === surfaces.length ? `All decided` : `Next undecided ${icon("arrow-right", 1.8)}`;
    }
  }

  function goTo(i) {
    if (!surfaces.length) return;
    current = Math.max(0, Math.min(surfaces.length - 1, i));
    markCurrent();
    surfaces[current].scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function nextUndecided() {
    const p = picks();
    for (let k = 1; k <= surfaces.length; k++) {
      const i = (current + k) % surfaces.length;
      if (!p[surfaces[i].dataset.surface]) return goTo(i);
    }
    toast("Every surface on this page has a pick");
  }

  function buildDock() {
    const dock = document.createElement("div");
    dock.className = "ax-dock";
    dock.innerHTML =
      `<span class="cnt"><span><b></b> decided</span><span class="bar"><i></i></span></span>` +
      `<button class="ax-btn" type="button" data-ax="next"></button>` +
      `<a class="ax-btn" href="index.html">Overview</a>` +
      `<button class="ax-btn" type="button" data-ax="keys" title="Keyboard shortcuts" aria-label="Keyboard shortcuts">?</button>`;
    const keys = document.createElement("div");
    keys.className = "ax-keys";
    keys.innerHTML = [
      ["Previous or next option", ["←", "→"]],
      ["Pick the option shown", ["P"]],
      ["Compare side by side", ["C"]],
      ["Next or previous surface", ["J", "K"]],
      ["Close", ["Esc"]],
    ].map(([t, k]) => `<span>${t}</span><kbd>${k.map((x) => `<span>${x}</span>`).join("")}</kbd>`).join("");
    document.body.append(dock, keys);
    dock.querySelector("[data-ax='next']").addEventListener("click", nextUndecided);
    dock.querySelector("[data-ax='keys']").addEventListener("click", () => keys.classList.toggle("on"));
  }

  /* zoom */
  let zoomEl = null;
  function buildZoom() {
    zoomEl = document.createElement("div");
    zoomEl.className = "ax-zoom";
    zoomEl.innerHTML = `<div class="ax-zoom-h"><span class="t"></span><button class="ax-btn" type="button">${icon("x", 1.8)}Close <kbd>Esc</kbd></button></div><div class="ax-zoom-in"></div>`;
    document.body.appendChild(zoomEl);
    zoomEl.querySelector(".ax-zoom-h .ax-btn").addEventListener("click", closeZoom);
    zoomEl.addEventListener("click", (e) => { if (e.target === zoomEl || e.target.classList.contains("ax-zoom-in")) closeZoom(); });
  }
  function openZoom(f, sec) {
    const dev = f.querySelector(":scope > .ax-dev").cloneNode(true);
    const box = document.createElement("div");
    box.className = "ax-frame ax-frame-p ax-frame-" + frameKind(f);
    box.dataset.frame = f.dataset.frame;
    box.appendChild(dev);
    const [w, h] = frameNat(f);
    const s = Math.min(1, (innerHeight - 120) / h, (innerWidth - 48) / w);
    sizeFrame(box, s);
    const opt = f.closest(".ax-opt");
    zoomEl.querySelector(".t").textContent = `${sec.dataset.title || ""} · ${opt ? opt.dataset.opt + ", " + (opt.dataset.name || "") : ""}`;
    const inner = zoomEl.querySelector(".ax-zoom-in");
    inner.innerHTML = "";
    inner.appendChild(box);
    zoomEl.classList.add("on");
    document.documentElement.style.overflow = "hidden";
  }
  function closeZoom() {
    if (!zoomEl || !zoomEl.classList.contains("on")) return false;
    zoomEl.classList.remove("on");
    zoomEl.querySelector(".ax-zoom-in").innerHTML = "";
    document.documentElement.style.overflow = "";
    return true;
  }

  function markCurrent() {
    surfaces.forEach((s, i) => s.classList.toggle("is-current", i === current));
  }
  function trackScroll() {
    let raf = 0;
    const upd = () => {
      const line = innerHeight * 0.4;
      let c = 0;
      surfaces.forEach((s, i) => { if (s.getBoundingClientRect().top <= line) c = i; });
      if (c !== current) { current = c; markCurrent(); }
    };
    addEventListener("scroll", () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(upd); }, { passive: true });
    upd();
  }

  function onKey(e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target;
    if (t && t.closest && t.closest("input, textarea, select, [contenteditable='true']")) return;
    if (e.key === "Escape") {
      if (closeZoom()) return;
      const k = document.querySelector(".ax-keys.on");
      if (k) { k.classList.remove("on"); return; }
      const sc = surfaces[current];
      if (sc && sc.classList.contains("is-compare")) toggleCompare(sc, false);
      return;
    }
    if (zoomEl && zoomEl.classList.contains("on")) return;
    if (e.key === "?") { document.querySelector(".ax-keys").classList.toggle("on"); return; }
    const sec = surfaces[current];
    if (!sec) return;
    const ids = sec._opts.map((o) => o.dataset.opt);
    const i = ids.indexOf(sec._active);
    switch (e.key) {
      case "ArrowRight": e.preventDefault(); setActive(sec, ids[(i + 1) % ids.length], true); break;
      case "ArrowLeft": e.preventDefault(); setActive(sec, ids[(i - 1 + ids.length) % ids.length], true); break;
      case "p": case "P": pick(sec, sec._active); break;
      case "c": case "C": toggleCompare(sec); break;
      case "j": case "J": goTo(current + 1); break;
      case "k": case "K": goTo(current - 1); break;
      default:
    }
  }

  function applyHash() {
    const h = decodeURIComponent(location.hash.slice(1));
    if (!h) return;
    const [id, opt] = h.split(":");
    const i = surfaces.findIndex((s) => s.id === id);
    if (i < 0) return;
    if (opt) setActive(surfaces[i], opt, false);
    current = i;
    markCurrent();
    requestAnimationFrame(() => surfaces[i].scrollIntoView({ block: "start" }));
  }

  function initViewer() {
    surfaces = [...document.querySelectorAll(".ax-surface")];
    document.body.classList.add("ax");
    buildTop();
    if (!surfaces.length) { render(document); return; }

    let main = document.querySelector("main.ax-main");
    if (!main) {
      main = document.createElement("main");
      main.className = "ax-main";
      const wrap = document.createElement("div");
      wrap.className = "ax-wrap";
      [...document.body.children].forEach((c) => {
        if (c.tagName === "SCRIPT" || c.classList.contains("ax-top") || c.classList.contains("ax-intro")) return;
        wrap.appendChild(c);
      });
      main.appendChild(wrap);
      const top = document.querySelector(".ax-top");
      const intro = document.querySelector(".ax-intro");
      (intro || top).after(main);
    }
    buildIntro(main);
    surfaces.forEach(setupSurface);

    const foot = document.createElement("footer");
    foot.className = "ax-foot";
    foot.innerHTML = `<div class="ax-wrap">Picks are saved in this browser only, apart from the web playground's. The overview collects them across every area.</div>`;
    main.after(foot);

    buildDock();
    buildZoom();
    refreshAll();
    surfaces.forEach(layoutSurface);
    render(document);
    applyHash();
    trackScroll();
    document.addEventListener("keydown", onKey);
    addEventListener("storage", (e) => { if (e.key === PK) refreshAll(); if (e.key === "ax-mode") setMode(currentMode(), false); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => surfaces.forEach(layoutSurface));
  }

  window.AX = {
    render,
    icon,
    logoMark,
    rng,
    series,
    fmtMoney,
    fmtPct,
    picks,
    metas,
    setMode,
    mode: currentMode,
    pages: PAGES,
    toast,
    statusBar,
    deviceHTML,
    NAT,
    PK,
    PKM,
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initViewer);
  else initViewer();
})();

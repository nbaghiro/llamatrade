#!/usr/bin/env python3
"""Builds app.html, the full-screen app viewer, from every area-*.html page in this folder.

Re-run it whenever an area page changes or a round-two page lands:
    python3 build-viewer.py
Pages that don't exist yet are skipped. app.html links kit.css and kit.js; everything else
(each page's styles, page scripts, templates and every option's frames) is inlined as data and
rendered one screen at a time inside an iframe, so pages never share CSS.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "app.html"

AREAS = [
    ("shell", "Shell"),
    ("home", "Home"),
    ("markets", "Markets"),
    ("strategies", "Strategies"),
    ("builder", "Builder"),
    ("backtests", "Backtests"),
    ("sessions", "Sessions"),
    ("portfolio", "Portfolio"),
    ("copilot", "Copilot"),
    ("account", "Account"),
    ("palette", "Gains and losses"),
]

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
RAW = {"script", "style", "textarea", "title"}
TAG_RE = re.compile(
    r"<(/?)([a-zA-Z][\w:-]*)((?:\s+[^\s=>/]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?)*)\s*(/?)>"
)
ATTR_RE = re.compile(r"([^\s=>/]+)(?:\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+))?")


@dataclass
class El:
    tag: str
    attrs: dict[str, str]
    start: int
    inner_start: int
    inner_end: int = -1
    end: int = -1
    parent: "El | None" = None
    children: list["El"] = field(default_factory=list)

    def has_class(self, c: str) -> bool:
        return c in self.attrs.get("class", "").split()

    def ancestors(self):
        p = self.parent
        while p is not None:
            yield p
            p = p.parent


def parse_attrs(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in ATTR_RE.finditer(s):
        v = m.group(2)
        if v is None:
            out[m.group(1)] = ""
        else:
            if v[:1] in "\"'":
                v = v[1:-1]
            out[m.group(1)] = html.unescape(v)
    return out


def parse(src: str) -> El:
    """Tolerant tag scanner that keeps raw source offsets for every element."""
    root = El("#root", {}, 0, 0)
    stack = [root]
    i = 0
    n = len(src)
    while i < n:
        lt = src.find("<", i)
        if lt < 0:
            break
        if src.startswith("<!--", lt):
            e = src.find("-->", lt + 4)
            i = n if e < 0 else e + 3
            continue
        if src.startswith("<!", lt):
            e = src.find(">", lt)
            i = n if e < 0 else e + 1
            continue
        m = TAG_RE.match(src, lt)
        if not m:
            i = lt + 1
            continue
        closing, tag, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if closing:
            for k in range(len(stack) - 1, 0, -1):
                if stack[k].tag == tag:
                    for j in range(len(stack) - 1, k, -1):
                        stack[j].inner_end = stack[j].end = lt
                    stack[k].inner_end, stack[k].end = lt, m.end()
                    del stack[k:]
                    break
            i = m.end()
            continue
        el = El(tag, parse_attrs(attrs), lt, m.end(), parent=stack[-1])
        stack[-1].children.append(el)
        if tag in VOID or selfclose:
            el.inner_end = el.end = m.end()
            i = m.end()
            continue
        if tag in RAW:
            close = re.compile(r"</" + tag + r"\s*>", re.I).search(src, m.end())
            el.inner_end = close.start() if close else n
            el.end = close.end() if close else n
            i = el.end
            continue
        stack.append(el)
        i = m.end()
    for el in stack[1:]:
        el.inner_end = el.end = n
    return root


def walk(el: El):
    for c in el.children:
        yield c
        yield from walk(c)


def inner(src: str, el: El) -> str:
    return src[el.inner_start : el.inner_end]


def outer(src: str, el: El) -> str:
    return src[el.start : el.end]


def short_title(t: str) -> str:
    return re.sub(r",?\s*round two\s*$", "", t, flags=re.I).strip()


def read_page(path: Path) -> dict:
    src = path.read_text(encoding="utf-8")
    root = parse(src)
    els = list(walk(root))
    body = next((e for e in els if e.tag == "body"), None)

    css = [inner(src, e) for e in els if e.tag == "style"]
    links = [
        e.attrs.get("href", "")
        for e in els
        if e.tag == "link" and "stylesheet" in e.attrs.get("rel", "") and e.attrs.get("href") != "kit.css"
    ]

    pre: list[str] = []
    post: list[str] = []
    seen_kit = False
    for e in els:
        if e.tag != "script" or body is None or not (body.start < e.start < body.end):
            continue
        if e.attrs.get("src", "").endswith("kit.js"):
            seen_kit = True
            continue
        if e.attrs.get("src") or e.attrs.get("type", "text/javascript") not in ("text/javascript", "module", ""):
            continue
        (post if seen_kit else pre).append(inner(src, e))

    def in_frame(e: El) -> bool:
        return any("data-frame" in a.attrs for a in e.ancestors())

    templates = "".join(outer(src, e) for e in els if e.tag == "template" and not in_frame(e))

    surfaces = []
    for sec in (e for e in els if e.has_class("ax-surface")):
        sid = sec.attrs.get("data-surface") or sec.attrs.get("id") or ""
        anchor = sec.attrs.get("id") or re.sub(r"[^a-z0-9]+", "-", sid.lower())
        opts = []
        for i, o in enumerate(c for c in sec.children if c.has_class("ax-opt")):
            frames = {"desktop": [], "phone": []}
            for f in walk(o):
                kind = f.attrs.get("data-frame")
                if kind not in frames or in_frame(f):
                    continue
                frames[kind].append(
                    {
                        "html": inner(src, f),
                        "cap": f.attrs.get("data-caption"),
                        "statusbar": f.attrs.get("data-statusbar") != "none",
                        "path": f.attrs.get("data-path"),
                    }
                )
            opts.append(
                {
                    "id": o.attrs.get("data-opt") or chr(65 + i),
                    "name": o.attrs.get("data-name", ""),
                    "note": o.attrs.get("data-note", ""),
                    "rec": "data-rec" in o.attrs,
                    "desk": frames["desktop"],
                    "phone": frames["phone"],
                }
            )
        if opts:
            surfaces.append(
                {
                    "sid": sid,
                    "anchor": anchor,
                    "title": sec.attrs.get("data-title") or sid,
                    "area": sec.attrs.get("data-area", ""),
                    "why": sec.attrs.get("data-why", ""),
                    "opts": opts,
                }
            )
    return {
        "title": body.attrs.get("data-title", path.stem) if body else path.stem,
        "css": "\n".join(css),
        "links": links,
        "pre": pre,
        "post": post,
        "tpl": templates,
        "surfaces": surfaces,
    }


def build() -> dict:
    pages: dict[str, dict] = {}
    screens: dict[str, dict] = {}
    areas = []
    for key, label in AREAS:
        r1_path, r2_path = HERE / f"area-{key}.html", HERE / f"area-{key}-2.html"
        rounds = []
        for rnd, p in ((1, r1_path), (2, r2_path)):
            if p.exists():
                data = read_page(p)
                pages[p.name] = {k: data[k] for k in ("title", "css", "links", "pre", "post", "tpl")}
                rounds.append((rnd, p.name, data["surfaces"]))
        if not rounds:
            continue

        def make_opts(page: str, s: dict, rnd: int, prefix: str = "") -> list[dict]:
            return [
                {
                    **o,
                    "key": prefix + o["id"],
                    "sid": s["sid"],
                    "page": page,
                    "anchor": s["anchor"],
                    "title": s["title"],
                    "areaName": s["area"],
                    "round": rnd,
                }
                for o in s["opts"]
            ]

        r1 = next(((pg, ss) for rnd, pg, ss in rounds if rnd == 1), None)
        r2 = next(((pg, ss) for rnd, pg, ss in rounds if rnd == 2), None)
        r1_by_sid = {s["sid"]: s for s in (r1[1] if r1 else [])}
        used: set[str] = set()
        order: list[str] = []

        if r2:
            for s in r2[1]:
                opts = make_opts(r2[0], s, 2)
                merged = None
                if s["sid"].endswith("2") and s["sid"][:-1] in r1_by_sid:
                    merged = r1_by_sid[s["sid"][:-1]]
                    used.add(merged["sid"])
                    opts += make_opts(r1[0], merged, 1, "1")
                screens[s["sid"]] = {
                    "sid": s["sid"],
                    "area": key,
                    "title": short_title(s["title"]),
                    "why": s["why"],
                    "round": 2,
                    "replaces": merged["sid"] if merged else None,
                    "opts": opts,
                }
                order.append(s["sid"])
        if r1:
            for s in r1[1]:
                if s["sid"] in used:
                    continue
                screens[s["sid"]] = {
                    "sid": s["sid"],
                    "area": key,
                    "title": short_title(s["title"]),
                    "why": s["why"],
                    "round": 1,
                    "replaces": None,
                    "opts": make_opts(r1[0], s, 1),
                }
                order.append(s["sid"])
        areas.append({"key": key, "label": label, "screens": order, "round2": bool(r2)})
    return {"areas": areas, "screens": screens, "pages": pages}


def main() -> None:
    data = build()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    OUT.write_text(SHELL_HTML.replace("/*__APP_DATA__*/null", payload), encoding="utf-8")
    n_opts = sum(len(s["opts"]) for s in data["screens"].values())
    print(f"app.html: {len(data['areas'])} areas, {len(data['screens'])} screens, {n_opts} options, {OUT.stat().st_size // 1024} KB")
    for a in data["areas"]:
        print(f"  {a['label']:<11} {len(a['screens']):>2} screens{'  (round two)' if a['round2'] else ''}")


SHELL_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LlamaTrade app</title>
<!-- Generated by build-viewer.py from the area-*.html pages. Edit those, then re-run the script. -->
<script>try{document.documentElement.dataset.mode=localStorage.getItem("ax-mode")||(matchMedia("(prefers-color-scheme: light)").matches?"light":"dark")}catch(e){document.documentElement.dataset.mode="dark"}</script>
<link rel="stylesheet" href="kit.css">
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; background: var(--x-bg); }
  body.ax { overflow: hidden; }
  .ax-top, .ax-foot { display: none !important; }
  #stage { position: fixed; inset: 0; }
  #stage iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; display: block; opacity: 0; transition: opacity 0.14s ease; background: var(--x-bg); }
  #stage iframe.on { opacity: 1; }

  .vb {
    position: fixed; left: 50%; bottom: 14px; z-index: 80; transform: translateX(-50%);
    display: flex; align-items: center; gap: 2px; height: 40px; padding: 0 5px; max-width: calc(100vw - 24px);
    border-radius: 999px; border: 1px solid var(--x-line-2);
    background: color-mix(in srgb, var(--panel) 82%, transparent);
    backdrop-filter: blur(14px) saturate(1.2); -webkit-backdrop-filter: blur(14px) saturate(1.2);
    box-shadow: 0 10px 34px -12px rgba(0, 0, 0, 0.45);
    font: 500 12.5px/1 var(--sans); color: var(--fg-2); white-space: nowrap;
    transition: opacity 0.35s ease;
  }
  .vb.dim { opacity: 0.3; }
  .vb:hover, .vb:focus-within { opacity: 1; }
  .vb.gone, .vw-pop.gone { display: none !important; }
  .vb button { all: unset; box-sizing: border-box; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 30px; min-width: 30px; padding: 0 8px; border-radius: 999px; color: var(--fg-2); }
  .vb button:hover { background: var(--sunk); color: var(--fg); }
  .vb button:focus-visible { outline: 1.5px solid var(--acc); outline-offset: 1px; }
  .vb button[disabled] { opacity: 0.35; cursor: default; background: none; }
  .vb svg { width: 16px; height: 16px; }
  .vb .sep { width: 1px; height: 18px; margin: 0 4px; background: var(--x-line-2); flex: none; }
  .vb .where { max-width: 300px; padding: 0 10px 0 12px; gap: 8px; }
  .vb .where .ar { color: var(--fg); font-weight: 600; }
  .vb .where .sc { overflow: hidden; text-overflow: ellipsis; min-width: 0; }
  .vb .where .ct { font: 400 11px var(--mono); color: var(--fg-3); }
  .vb .opts .grp { font: 500 10px var(--mono); color: var(--fg-3); margin: 0 4px 0 2px; text-transform: uppercase; letter-spacing: .06em; }
  .vb .oname { font-size: 12.5px; color: var(--fg); max-width: 260px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-left: 6px; }
  .vb .oname i { font-style: normal; font: 500 10px var(--mono); color: var(--acc); margin-left: 6px; text-transform: uppercase; letter-spacing: .06em; }
  .vb .opts { display: flex; align-items: center; gap: 1px; }
  .vb .opts button { position: relative; min-width: 28px; padding: 0 7px; font: 500 12px var(--mono); }
  .vb .opts button.on { background: var(--ink); color: var(--ink-text); }
  .vb .opts button.r1 { font-size: 11px; color: var(--fg-3); }
  .vb .opts button.r1.on { color: var(--ink-text); }
  .vb .opts button.pk::after { content: ""; position: absolute; top: 3px; right: 3px; width: 5px; height: 5px; border-radius: 50%; background: var(--acc); box-shadow: 0 0 0 1.5px var(--panel); }
  .vb .opts button.rec::before { content: ""; position: absolute; bottom: 3px; left: 50%; width: 10px; height: 1.5px; margin-left: -5px; border-radius: 2px; background: currentColor; opacity: 0.55; }
  .vb .opts .gap { width: 1px; height: 14px; margin: 0 4px; background: var(--x-line-2); }
  .vb .pick { padding: 0 11px; color: var(--fg); }
  .vb .pick.picked { color: var(--acc); }
  .vb .pick kbd, .vb .where kbd { font: 400 10.5px var(--mono); opacity: 0.5; }
  .vb .note { font: 400 11px var(--sans); color: var(--fg-3); padding: 0 4px; }

  .vw-pop {
    position: fixed; left: 50%; bottom: 66px; z-index: 81; transform: translateX(-50%);
    width: min(560px, calc(100vw - 24px)); padding: 16px 18px 14px; border-radius: 14px;
    border: 1px solid var(--x-line-2); background: color-mix(in srgb, var(--panel) 94%, transparent);
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    box-shadow: 0 18px 50px -16px rgba(0, 0, 0, 0.5);
    font: 400 13.5px/1.55 var(--sans); color: var(--fg-2); display: none;
  }
  .vw-pop.on { display: block; }
  .vw-pop h3 { margin: 0 0 6px; font: 600 14.5px/1.3 var(--sans); color: var(--fg); letter-spacing: -0.01em; }
  .vw-pop p { margin: 0 0 8px; }
  .vw-pop .meta { display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: center; margin-top: 10px; font-size: 12px; color: var(--fg-3); }
  .vw-pop .tag { padding: 2px 8px; border-radius: 999px; border: 1px solid var(--x-line-2); font-size: 11.5px; }
  .vw-pop .tag.acc { border-color: var(--acc); color: var(--acc); }
  .vw-pop a { color: var(--fg); text-decoration: underline; text-underline-offset: 3px; text-decoration-color: var(--x-line-2); }
  .vw-pop .why { color: var(--fg-3); font-size: 12.5px; }

  .vw-ov { position: fixed; inset: 0; z-index: 90; display: none; background: var(--scrim); backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px); }
  .vw-ov.on { display: block; }
  .vw-ov .box {
    position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
    width: min(1180px, calc(100vw - 32px)); max-height: calc(100vh - 90px); overflow: auto;
    padding: 22px 24px 18px; border-radius: 16px; border: 1px solid var(--x-line-2);
    background: var(--panel); box-shadow: 0 30px 80px -24px rgba(0, 0, 0, 0.55); font: 400 13px/1.4 var(--sans); color: var(--fg-2);
  }
  .vw-ov .hd { display: flex; align-items: baseline; gap: 14px; margin-bottom: 16px; }
  .vw-ov .hd b { font: 600 17px var(--sans); color: var(--fg); letter-spacing: -0.015em; }
  .vw-ov .hd span { font: 400 12px var(--mono); color: var(--fg-3); }
  .vw-ov .hd a { margin-left: auto; font-size: 12.5px; color: var(--fg-2); text-decoration: none; }
  .vw-ov .hd a:hover { color: var(--fg); }
  .vw-ov .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 18px 16px; }
  .vw-ov .ar h4 { margin: 0 0 6px; display: flex; align-items: baseline; gap: 8px; font: 600 13px var(--sans); color: var(--fg); }
  .vw-ov .ar h4 i { font: 400 11px var(--mono); font-style: normal; color: var(--fg-3); }
  .vw-ov .ar button { all: unset; box-sizing: border-box; cursor: pointer; display: flex; align-items: center; gap: 8px; width: 100%; padding: 3px 8px; margin-left: -8px; border-radius: 7px; }
  .vw-ov .ar button:hover { background: var(--sunk); color: var(--fg); }
  .vw-ov .ar button.cur { background: var(--acc-soft); color: var(--fg); }
  .vw-ov .ar button .t { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .vw-ov .ar button b { font: 500 11px var(--mono); color: var(--fg-4); }
  .vw-ov .ar button.done b { color: var(--acc); }
  .vw-ov .ar button .n2 { font: 400 10px var(--mono); color: var(--fg-3); border: 1px solid var(--x-line-2); border-radius: 4px; padding: 0 3px; }
  .vw-ov .keys { margin-top: 18px; padding-top: 12px; border-top: 1px solid var(--x-line); display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 12px; color: var(--fg-3); }
  .vw-ov .keys kbd { font: 500 11px var(--mono); color: var(--fg-2); border: 1px solid var(--x-line-2); border-bottom-width: 2px; border-radius: 4px; padding: 0 5px; margin-right: 4px; }

  @media (max-width: 760px) {
    .vb .where .sc, .vb .note { display: none; }
  }
</style>
</head>
<body>
<div id="stage"></div>

<div class="vb" id="vb" role="toolbar" aria-label="App viewer">
  <button class="where" type="button" data-a="ov" title="All screens (O)"><span class="ar"></span><span class="sc"></span><span class="ct"></span></button>
  <span class="sep"></span>
  <button type="button" data-a="prev" title="Previous screen (←)" aria-label="Previous screen"></button>
  <button type="button" data-a="next" title="Next screen (→)" aria-label="Next screen"></button>
  <span class="sep"></span>
  <div class="opts" role="group" aria-label="Options"></div>
  <span class="oname"></span>
  <button class="pick" type="button" data-a="pick" title="Pick this option (P)"></button>
  <span class="sep"></span>
  <span class="note"></span>
  <button type="button" data-a="device" title="Desktop or phone (M)" aria-label="Desktop or phone"></button>
  <button type="button" data-a="theme" title="Light or dark (T)" aria-label="Light or dark"></button>
  <button type="button" data-a="info" title="About this option (I)" aria-label="About this option"></button>
</div>
<div class="vw-pop" id="info" role="dialog" aria-label="About this option"></div>
<div class="vw-ov" id="ov" role="dialog" aria-label="All screens"><div class="box"></div></div>

<script type="application/json" id="app-data">/*__APP_DATA__*/null</script>
<script src="kit.js"></script>
<script>
(function () {
  "use strict";
  const DATA = JSON.parse(document.getElementById("app-data").textContent);
  const AX = window.AX;
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    raw(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, typeof v === "string" ? v : JSON.stringify(v)); } catch (e) { /* storage blocked */ } },
  };
  const picks = () => store.get("ax-picks", {});
  const metas = () => store.get("ax-picks-meta", {});

  const FLOW = [];
  DATA.areas.forEach((a) => a.screens.forEach((sid) => FLOW.push(sid)));
  const AREA = Object.fromEntries(DATA.areas.map((a) => [a.key, a]));
  const browsing = {};
  let idx = 0;
  let device = store.raw("ax-viewer-device") === "phone" ? "phone" : "desktop";

  const STATUS_BAR =
    '<span>9:41</span><span class="r">' +
    '<svg width="18" height="11" viewBox="0 0 18 11" fill="currentColor"><rect x="0" y="7" width="3" height="4" rx="0.8"/><rect x="5" y="5" width="3" height="6" rx="0.8"/><rect x="10" y="2.5" width="3" height="8.5" rx="0.8"/><rect x="15" y="0" width="3" height="11" rx="0.8"/></svg>' +
    '<svg width="16" height="11" viewBox="0 0 16 11" fill="currentColor"><path d="M8 2.2c2.3 0 4.4.9 6 2.4l1.1-1.2A10.3 10.3 0 0 0 8 .6 10.3 10.3 0 0 0 .9 3.4L2 4.6a8.6 8.6 0 0 1 6-2.4Zm0 3.3c1.4 0 2.6.5 3.6 1.4l1.1-1.2A6.9 6.9 0 0 0 8 3.9a6.9 6.9 0 0 0-4.7 1.8l1.1 1.2c1-.9 2.2-1.4 3.6-1.4Zm0 3.2c.5 0 1 .2 1.3.5L8 10.6 6.7 9.2c.3-.3.8-.5 1.3-.5Z"/></svg>' +
    '<svg width="27" height="13" viewBox="0 0 27 13" fill="none"><rect x="0.5" y="0.5" width="23" height="12" rx="3.5" stroke="currentColor" opacity="0.4"/><rect x="2" y="2" width="18" height="9" rx="2" fill="currentColor"/><path d="M25 4.5v4c.8-.3 1.3-1.1 1.3-2s-.5-1.7-1.3-2Z" fill="currentColor" opacity="0.45"/></svg>' +
    "</span>";

  /* Runs inside each screen document: fits the frame to the window, forwards keys and app clicks. */
  const FRAME_CSS = `
    html, body { margin: 0; height: 100%; overflow: hidden; background: var(--x-bg); }
    .ax-top, .ax-foot, .ax-dock, .ax-keys, .ax-zoom, .ax-toast { display: none !important; }
    .vw-win.ax-win { position: fixed; left: 0; top: 0; border: 0; border-radius: 0; box-shadow: none; transform-origin: 0 0; }
    .vw-win.ax-win::before { display: none; }
    .vw-win .ax-win-scr > .app .main { overflow-x: hidden; overflow-y: auto; scrollbar-width: thin; }
    .topbar .nav a, .m-tabs > a, .topbar .avatar, .topbar .logo, .topbar .h-bell { cursor: pointer; }
    .vw-stage { position: fixed; inset: 0; overflow: hidden; background: var(--x-bg); }
    .vw-stage > .art { height: 74%; }
    .vw-stage > .glow { height: 100%; }
    .vw-phones { position: absolute; inset: 0; z-index: 1; display: flex; align-items: center; justify-content: center; gap: 56px; padding-bottom: 40px; }
    .vw-ph { position: relative; flex: none; }
    .vw-ph > .ax-dev { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
    .vw-ph > .cap { position: absolute; left: 0; right: 0; bottom: -26px; text-align: center; font: 400 11.5px var(--mono); color: var(--fg-3); white-space: nowrap; }
  `;
  const TB_SCRIPT = `(function () {
    var DEF = ["Home", "Strategies", "Backtests", "Sessions", "Portfolio", "Copilot"];
    document.querySelectorAll("[data-tb]:not(.topbar)").forEach(function (el) {
      var NAV = el.getAttribute("data-nav") ? el.getAttribute("data-nav").split(",") : DEF;
      var on = el.getAttribute("data-tb") || "Home";
      var mkt = el.getAttribute("data-mkt") || "Market open · 10:42 ET";
      var closed = el.hasAttribute("data-closed") ? " closed" : "";
      var bell = el.getAttribute("data-bell");
      var extra = el.innerHTML;
      el.classList.add("topbar");
      el.innerHTML =
        '<span data-logo data-size="34" class="overhang"></span><nav class="nav">' +
        NAV.map(function (n) { return "<a" + (n === on ? ' class="on"' : "") + ">" + n + "</a>"; }).join("") +
        '</nav><div class="end">' + extra + '<span class="mkt' + closed + '">' + mkt + "</span>" +
        '<span class="btn icon ghost sm h-bell"><span data-icon="bell"></span>' + (bell ? "<b>" + bell + "</b>" : "") + "</span>" +
        '<span class="avatar">SR</span></div>';
    });
  })();`;
  const BRIDGE = (id) => `(function () {
    var ID = ${id}, MINW = 1280, PW = 412, PH = 866;
    function post(m) { m.vw = m.vw || "x"; m.id = ID; try { parent.postMessage(m, "*"); } catch (e) {} }
    function fit() {
      var win = document.querySelector(".vw-win");
      if (win) {
        var s = Math.min(1, innerWidth / MINW);
        win.style.width = (innerWidth / s) + "px";
        win.style.height = (innerHeight / s) + "px";
        win.style.transform = s < 1 ? "scale(" + s + ")" : "";
      }
      var ph = document.querySelectorAll(".vw-ph");
      if (ph.length) {
        var k = ph.length, gap = 56 * (k - 1);
        var cap = document.querySelector(".vw-ph > .cap") ? 40 : 0;
        var s2 = Math.min(1, (innerHeight - 110 - cap) / PH, (innerWidth - 48 - gap) / (k * PW));
        ph.forEach(function (p) {
          p.style.width = PW * s2 + "px";
          p.style.height = PH * s2 + "px";
          p.firstElementChild.style.transform = "scale(" + s2 + ")";
        });
      }
    }
    fit();
    addEventListener("resize", fit);
    var MAP = { home: 1, markets: 1, strategies: 1, backtests: 1, sessions: 1, portfolio: 1, copilot: 1, account: 1 };
    document.addEventListener("click", function (e) {
      var t = e.target && e.target.closest ? e.target : null;
      if (!t) return;
      var a = t.closest(".topbar .nav a, .m-tabs > a");
      if (a) { var k = a.textContent.trim().toLowerCase(); if (MAP[k]) post({ vw: "nav", area: k }); return; }
      if (t.closest(".topbar .avatar")) { post({ vw: "nav", area: "account" }); return; }
      if (t.closest(".topbar .logo, .topbar [data-logo]")) { post({ vw: "nav", area: "home" }); return; }
      if (t.closest(".topbar .h-bell, .topbar [data-icon='bell']")) { post({ vw: "nav", screen: "shell/notifications" }); }
    }, true);
    var KEYS = /^(ArrowLeft|ArrowRight|[1-9]|[pPmMtTiIoOhH]|Escape)$/;
    document.addEventListener("keydown", function (e) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      var t = e.target;
      if (t && t.closest && t.closest("input, textarea, select, [contenteditable='true']")) return;
      if (!KEYS.test(e.key)) return;
      e.preventDefault();
      post({ vw: "key", key: e.key });
    });
    var last = 0;
    document.addEventListener("mousemove", function (e) {
      var now = Date.now();
      if (now - last < 150) return;
      last = now;
      post({ vw: "move", y: e.clientY / innerHeight });
    }, { passive: true });
    addEventListener("message", function (e) {
      var d = e.data || {};
      if (d.vw === "mode" && window.AX) { window.AX.setMode(d.mode, false); }
    });
    addEventListener("load", function () {
      requestAnimationFrame(function () {
        if (window.AX) window.AX.render(document);
        requestAnimationFrame(function () { post({ vw: "ready" }); });
      });
    });
  })();`;

  /* ------------------------------------------------------------ model */
  function screenAt(i) { return DATA.screens[FLOW[i]]; }
  function optByKey(sc, key) { return sc.opts.find((o) => o.key === key); }
  function defaultKey(sc) {
    const p = picks();
    const r2 = sc.opts.filter((o) => o.sid === sc.sid);
    if (p[sc.sid] && r2.some((o) => o.id === p[sc.sid])) return r2.find((o) => o.id === p[sc.sid]).key;
    if (sc.replaces && p[sc.replaces]) {
      const o = sc.opts.find((x) => x.sid === sc.replaces && x.id === p[sc.replaces]);
      if (o) return o.key;
    }
    const rec = r2.find((o) => o.rec);
    return (rec || sc.opts[0]).key;
  }
  function activeKey(sc) {
    if (!browsing[sc.sid] || !optByKey(sc, browsing[sc.sid])) browsing[sc.sid] = defaultKey(sc);
    return browsing[sc.sid];
  }
  function isPicked(o) { return picks()[o.sid] === o.id; }
  function decided(sc) { const p = picks(); return !!(p[sc.sid] || (sc.replaces && p[sc.replaces])); }

  /* ------------------------------------------------------------ screen documents */
  let seq = 0;
  function frameMarkup(o) {
    const wantDesk = device === "desktop";
    const useDesk = (wantDesk && o.desk.length > 0) || o.phone.length === 0;
    if (useDesk) {
      return { kind: "desktop", fallback: !wantDesk, html: `<div class="ax-dev ax-win vw-win"><div class="ax-win-scr">${o.desk[0].html}</div></div>` };
    }
    const seed = 2611 + FLOW.indexOf(screenAt(idx).sid) * 37;
    const phones = o.phone.map((f) => {
      const sb = f.statusbar ? `<div class="sb">${STATUS_BAR}</div>` : "";
      const cap = o.phone.length > 1 && f.cap ? `<div class="cap">${esc(f.cap)}</div>` : "";
      return `<div class="vw-ph"><div class="ax-dev ax-phone"><div class="ax-phone-scr">${sb}${f.html}<i class="hi"></i></div></div>${cap}</div>`;
    }).join("");
    return {
      kind: "phone",
      fallback: wantDesk,
      html: `<div class="vw-stage"><div class="art" data-art="candles" data-seed="${seed}"></div><div class="glow"></div><div class="vw-phones">${phones}</div></div>`,
    };
  }
  function docFor(o, id) {
    const pg = DATA.pages[o.page];
    const fm = frameMarkup(o);
    const mode = document.documentElement.dataset.mode || "dark";
    const scripts = (list) => list.map((s) => `<script>${s}<\/script>`).join("\n");
    const html =
      `<!doctype html><html lang="en" data-mode="${mode}"><head><meta charset="utf-8">` +
      `<link rel="stylesheet" href="kit.css">` +
      pg.links.map((h) => `<link rel="stylesheet" href="${esc(h)}">`).join("") +
      `<style>${pg.css}</style><style>${FRAME_CSS}</style></head><body>` +
      fm.html + pg.tpl +
      `<script>${BRIDGE(id)}<\/script>` +
      scripts(pg.pre) +
      `<script>${TB_SCRIPT}<\/script>` +
      `<script src="kit.js"><\/script>` +
      scripts(pg.post) +
      `</body></html>`;
    return { html, fm };
  }

  const stage = $("#stage");
  let pendingId = 0;
  function mount() {
    const sc = screenAt(idx);
    const o = optByKey(sc, activeKey(sc));
    const id = ++seq;
    const { html, fm } = docFor(o, id);
    const f = document.createElement("iframe");
    f.dataset.id = String(id);
    f.title = `${sc.title}, option ${o.key}`;
    f.srcdoc = html;
    stage.appendChild(f);
    pendingId = id;
    setTimeout(() => reveal(id), 2500);
    lastFrame = fm;
    renderBar();
  }
  let lastFrame = null;
  function reveal(id) {
    const f = stage.querySelector(`iframe[data-id="${id}"]`);
    if (!f || f.classList.contains("on") || id !== pendingId) return;
    f.classList.add("on");
    setTimeout(() => {
      const ae = document.activeElement;
      const hadFocus = ae && ae.tagName === "IFRAME" && ae !== f;
      stage.querySelectorAll("iframe").forEach((x) => { if (x !== f) x.remove(); });
      if (hadFocus) { try { f.contentWindow.focus(); } catch (e) { window.focus(); } }
    }, 160);
  }
  function currentFrame() { return stage.querySelector(`iframe[data-id="${pendingId}"]`); }

  /* ------------------------------------------------------------ navigation */
  function writeHash() {
    const sc = screenAt(idx);
    try { history.replaceState(null, "", "#" + sc.sid + ":" + activeKey(sc)); } catch (e) { /* file url */ }
  }
  function go(i, key) {
    if (i < 0 || i >= FLOW.length) {
      AX.toast(i < 0 ? "This is the first screen" : "This is the last screen");
      return;
    }
    idx = i;
    const sc = screenAt(idx);
    if (key && optByKey(sc, key)) browsing[sc.sid] = key;
    closePops();
    writeHash();
    mount();
  }
  function goSid(sid, key) { const i = FLOW.indexOf(sid); if (i >= 0) go(i, key); }
  function goArea(k) { const a = AREA[k]; if (a && a.screens.length) goSid(a.screens[0]); }
  function setOpt(key) {
    const sc = screenAt(idx);
    if (!optByKey(sc, key) || activeKey(sc) === key) return;
    browsing[sc.sid] = key;
    writeHash();
    mount();
  }
  function applyHash() {
    const h = decodeURIComponent(location.hash.slice(1));
    if (!h) return false;
    const [sid, key] = h.split(":");
    let i = FLOW.indexOf(sid);
    if (i < 0) {
      const via = FLOW.findIndex((x) => DATA.screens[x].replaces === sid);
      if (via < 0) return false;
      i = via;
      if (key) browsing[FLOW[i]] = "1" + key;
      go(i);
      return true;
    }
    go(i, key);
    return true;
  }

  /* ------------------------------------------------------------ picks */
  function pick() {
    const sc = screenAt(idx);
    const o = optByKey(sc, activeKey(sc));
    const p = picks(), m = metas();
    if (p[o.sid] === o.id) {
      delete p[o.sid];
      delete m[o.sid];
      AX.toast(`Pick cleared for ${o.title}`);
    } else {
      p[o.sid] = o.id;
      m[o.sid] = { title: o.title, area: o.areaName || "", option: o.name || o.id, optionId: o.id, note: o.note || "", page: o.page, anchor: o.anchor, at: new Date().toISOString() };
      AX.toast(`Picked ${o.id}, ${o.name || ""}`);
    }
    store.set("ax-picks", p);
    store.set("ax-picks-meta", m);
    renderBar();
    if ($("#ov").classList.contains("on")) renderOverview();
  }

  /* ------------------------------------------------------------ control bar */
  const vb = $("#vb");
  vb.querySelector('[data-a="prev"]').innerHTML = AX.icon("chevron-left", 1.8);
  vb.querySelector('[data-a="next"]').innerHTML = AX.icon("chevron-right", 1.8);
  vb.querySelector('[data-a="info"]').innerHTML = AX.icon("info", 1.7);

  function renderBar() {
    const sc = screenAt(idx);
    const a = AREA[sc.area];
    const key = activeKey(sc);
    const o = optByKey(sc, key);
    const pos = a.screens.indexOf(sc.sid) + 1;
    $(".where .ar", vb).textContent = a.label;
    $(".where .sc", vb).textContent = sc.title;
    $(".where .ct", vb).textContent = `${pos}/${a.screens.length}`;
    vb.querySelector('[data-a="prev"]').disabled = idx === 0;
    vb.querySelector('[data-a="next"]').disabled = idx === FLOW.length - 1;
    const p = picks();
    let prevRound = sc.opts[0].round;
    $(".opts", vb).innerHTML = sc.opts.map((x, i) => {
      const gap = x.round !== prevRound ? '<span class="gap"></span><span class="grp">Round one</span>' : "";
      prevRound = x.round;
      const cls = [x.key === key ? "on" : "", p[x.sid] === x.id ? "pk" : "", x.rec ? "rec" : "", x.round === 1 && sc.round === 2 ? "r1" : ""].join(" ");
      const tip = `${x.round === 1 && sc.round === 2 ? "Round one, " : ""}${x.id}. ${x.name}${x.rec ? " (recommended)" : ""}${p[x.sid] === x.id ? ", picked" : ""}${i < 9 ? ` (${i + 1})` : ""}`;
      return `${gap}<button type="button" class="${cls}" data-k="${esc(x.key)}" title="${esc(tip)}" aria-pressed="${x.key === key}">${esc(x.key)}</button>`;
    }).join("");
    const pb = vb.querySelector('[data-a="pick"]');
    const picked = isPicked(o);
    pb.classList.toggle("picked", picked);
    pb.innerHTML = picked ? `${AX.icon("check", 2)}Picked <kbd>P</kbd>` : `Pick ${esc(o.key)} <kbd>P</kbd>`;
    vb.querySelector('[data-a="device"]').innerHTML = device === "phone"
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 18h2"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4.5" width="18" height="12" rx="1.5"/><path d="M9 20h6M12 16.5V20"/></svg>';
    vb.querySelector('[data-a="device"]').title = device === "phone" ? "Phone. Switch to desktop (M)" : "Desktop. Switch to phone (M)";
    const mode = document.documentElement.dataset.mode;
    vb.querySelector('[data-a="theme"]').innerHTML = AX.icon(mode === "light" ? "sun" : "moon", 1.7);
    vb.querySelector('[data-a="theme"]').title = mode === "light" ? "Light. Switch to dark (T)" : "Dark. Switch to light (T)";
    $(".oname", vb).innerHTML = `${esc(o.name)}${o.rec ? ' <i>Recommended</i>' : ""}`;
    const fb = lastFrame && lastFrame.fallback;
    $(".note", vb).textContent = fb ? (lastFrame.kind === "phone" ? "No desktop view, showing phone" : "No phone view, showing desktop") : "";
    document.title = `${sc.title} · ${a.label} · LlamaTrade`;
    if ($("#info").classList.contains("on")) renderInfo();
    wake();
  }

  vb.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.k) { setOpt(b.dataset.k); return; }
    const a = b.dataset.a;
    if (a === "prev") go(idx - 1);
    else if (a === "next") go(idx + 1);
    else if (a === "pick") pick();
    else if (a === "device") toggleDevice();
    else if (a === "theme") toggleTheme();
    else if (a === "info") toggleInfo();
    else if (a === "ov") toggleOverview();
  });

  function toggleDevice() {
    device = device === "phone" ? "desktop" : "phone";
    store.set("ax-viewer-device", device);
    mount();
  }
  function toggleTheme() {
    const m = document.documentElement.dataset.mode === "light" ? "dark" : "light";
    AX.setMode(m, true);
    const f = currentFrame();
    if (f && f.contentWindow) f.contentWindow.postMessage({ vw: "mode", mode: m }, "*");
    renderBar();
  }

  /* info */
  function renderInfo() {
    const sc = screenAt(idx);
    const o = optByKey(sc, activeKey(sc));
    const tags = [];
    if (o.rec) tags.push('<span class="tag acc">Recommended</span>');
    if (isPicked(o)) tags.push('<span class="tag acc">Picked</span>');
    if (o.round === 1 && sc.round === 2) tags.push('<span class="tag">Round one</span>');
    const href = `${o.page}#${o.anchor}:${o.id}`;
    $("#info").innerHTML =
      `<h3>${esc(o.id)}. ${esc(o.name || "Option " + o.id)}</h3>` +
      (o.note ? `<p>${esc(o.note)}</p>` : "") +
      (sc.why ? `<p class="why">${esc(sc.why)}</p>` : "") +
      `<div class="meta">${tags.join("")}<a href="${esc(href)}">Open on the area page</a></div>`;
  }
  function toggleInfo(force) {
    const el = $("#info");
    const on = force != null ? force : !el.classList.contains("on");
    if (on) { $("#ov").classList.remove("on"); renderInfo(); }
    el.classList.toggle("on", on);
  }

  /* overview */
  function renderOverview() {
    const p = picks();
    const total = FLOW.length, done = FLOW.filter((s) => decided(DATA.screens[s])).length;
    const cur = screenAt(idx).sid;
    const areas = DATA.areas.map((a) => {
      const d = a.screens.filter((s) => decided(DATA.screens[s])).length;
      const rows = a.screens.map((sid) => {
        const sc = DATA.screens[sid];
        const v = p[sid] || (sc.replaces && p[sc.replaces] ? "1" + p[sc.replaces] : "");
        return `<button type="button" data-sid="${esc(sid)}" class="${sid === cur ? "cur" : ""} ${v ? "done" : ""}"><span class="t">${esc(sc.title)}</span>${sc.round === 2 ? '<span class="n2" title="Round two">2</span>' : ""}<b>${v ? esc(v) : "·"}</b></button>`;
      }).join("");
      return `<div class="ar"><h4>${esc(a.label)}<i>${d} of ${a.screens.length}</i></h4>${rows}</div>`;
    }).join("");
    $("#ov .box").innerHTML =
      `<div class="hd"><b>All screens</b><span>${done} of ${total} decided</span><a href="index.html">Back to the overview page</a></div>` +
      `<div class="grid">${areas}</div>` +
      `<div class="keys"><span><kbd>←</kbd><kbd>→</kbd>screens</span><span><kbd>1</kbd>to<kbd>9</kbd> options</span><span><kbd>P</kbd>pick</span><span><kbd>M</kbd>desktop or phone</span><span><kbd>T</kbd>light or dark</span><span><kbd>I</kbd>about the option</span><span><kbd>O</kbd>this list</span><span><kbd>H</kbd>hide the controls</span></div>`;
  }
  function toggleOverview(force) {
    const el = $("#ov");
    const on = force != null ? force : !el.classList.contains("on");
    if (on) { $("#info").classList.remove("on"); renderOverview(); }
    el.classList.toggle("on", on);
  }
  $("#ov").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-sid]");
    if (b) { toggleOverview(false); goSid(b.dataset.sid); return; }
    if (e.target === e.currentTarget) toggleOverview(false);
  });
  function closePops() {
    const any = $("#info").classList.contains("on") || $("#ov").classList.contains("on");
    toggleInfo(false);
    toggleOverview(false);
    return any;
  }

  /* hide and dim */
  let hidden = false, dimTimer = 0;
  function wake() {
    vb.classList.remove("dim");
    clearTimeout(dimTimer);
    dimTimer = setTimeout(() => { if (!$("#info").classList.contains("on")) vb.classList.add("dim"); }, 2600);
  }
  function toggleHide() {
    hidden = !hidden;
    vb.classList.toggle("gone", hidden);
    $("#info").classList.toggle("gone", hidden);
    if (!hidden) wake();
  }
  addEventListener("mousemove", (e) => { if (e.clientY > innerHeight - 140) wake(); }, { passive: true });

  /* keys */
  function onKey(key) {
    if (key === "Escape") { closePops(); return; }
    if (key === "o" || key === "O") { toggleOverview(); return; }
    if (key === "h" || key === "H") { toggleHide(); return; }
    if ($("#ov").classList.contains("on")) return;
    const sc = screenAt(idx);
    if (/^[1-9]$/.test(key)) { const o = sc.opts[+key - 1]; if (o) setOpt(o.key); return; }
    switch (key) {
      case "ArrowRight": go(idx + 1); break;
      case "ArrowLeft": go(idx - 1); break;
      case "p": case "P": pick(); break;
      case "m": case "M": toggleDevice(); break;
      case "t": case "T": toggleTheme(); break;
      case "i": case "I": toggleInfo(); break;
      default: return;
    }
    if (!hidden) wake();
  }
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (!/^(ArrowLeft|ArrowRight|[1-9]|[pPmMtTiIoOhH]|Escape)$/.test(e.key)) return;
    e.preventDefault();
    onKey(e.key);
  });

  addEventListener("message", (e) => {
    const d = e.data || {};
    if (!d.vw) return;
    const f = currentFrame();
    if (d.vw === "ready") { reveal(d.id); return; }
    if (!f || e.source !== f.contentWindow) return;
    if (d.vw === "key") onKey(d.key);
    else if (d.vw === "move") { if (d.y > 0.82) wake(); }
    else if (d.vw === "nav") {
      if (d.screen) goSid(d.screen);
      else if (d.area) goArea(d.area);
    }
  });

  let rz = 0;
  addEventListener("resize", () => {
    clearTimeout(rz);
    rz = setTimeout(() => { if (lastFrame && lastFrame.kind === "desktop") mount(); }, 260);
  });
  addEventListener("hashchange", () => {
    const sc = screenAt(idx);
    if (location.hash.slice(1) !== encodeURI(sc.sid + ":" + activeKey(sc)) && decodeURIComponent(location.hash.slice(1)) !== sc.sid + ":" + activeKey(sc)) applyHash();
  });
  addEventListener("storage", (e) => {
    if (e.key === "ax-picks") renderBar();
    if (e.key === "ax-mode") { AX.setMode(AX.mode(), false); renderBar(); }
  });

  if (!FLOW.length) {
    $(".where .sc", vb).textContent = "No area pages found. Run build-viewer.py next to the area pages.";
    return;
  }
  if (!applyHash()) go(0);
})();
</script>
</body>
</html>
'''

if __name__ == "__main__":
    main()

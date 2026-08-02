"""Render every transactional-email scenario with demo data into one gallery.

A local design/QA harness — not shipped. Uses the real send path
(``templates.render`` → ``email_render.build_html`` over the committed
``email_html/`` shells), so what you see is what recipients get. Run:

    cd services/notification && ../../.venv/bin/python tools/preview_emails.py [--open]

Writes ``tools/email_preview.html`` (gitignored) and, with ``--open``, opens it.
"""

from __future__ import annotations

import base64
import html
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llamatrade_proto.generated import events_pb2 as e

from src.email_render import build_html
from src.preferences import effective_severity
from src.templates import render

# Inline the header logo as a data URI so the gallery is self-contained (the real
# send path fills __LOGO_URL__ from EMAIL_ASSET_BASE_URL against a served host).
os.environ["EMAIL_ASSET_BASE_URL"] = "https://preview.local"
_LOGO_URL = "https://preview.local/logo-monolith.png"
_LOGO_DATA_URI = "data:image/png;base64," + base64.b64encode(
    (Path(__file__).resolve().parents[3] / "apps/web/public/logo-monolith.png").read_bytes()
).decode()

_SEVERITY_NAME = {
    e.NOTIFICATION_SEVERITY_INFO: "info",
    e.NOTIFICATION_SEVERITY_ACTIONABLE: "actionable",
    e.NOTIFICATION_SEVERITY_CRITICAL: "critical",
    e.NOTIFICATION_SEVERITY_SECURITY: "security",
}

# Demo machine fields; producers send these, templates compose the copy.
_DEMO = {
    "symbol": "AAPL",
    "amount": "12,500.00",
    "reason": "insufficient buying power",
    "extra": {"link": "https://app.llamatrade.ai/action?token=demo-9f2a1c"},
}


def _demo_event(category: int) -> e.NotificationEvent:
    return e.NotificationEvent(
        category=category,
        severity=e.NOTIFICATION_SEVERITY_UNSPECIFIED,
        symbol=_DEMO["symbol"],
        amount=_DEMO["amount"],
        reason=_DEMO["reason"],
        extra=_DEMO["extra"],
    )


def _categories() -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for name in dir(e):
        if not name.startswith("NOTIFICATION_CATEGORY_"):
            continue
        value = getattr(e, name)
        if name.endswith("_UNSPECIFIED") or value == 0:
            continue
        out.append((name.removeprefix("NOTIFICATION_CATEGORY_"), value))
    return sorted(out)


def _card(label: str, severity: str, subject: str, body_html: str) -> str:
    srcdoc = html.escape(body_html, quote=True)
    return f"""
    <section class="card sev-{severity}">
      <header>
        <span class="badge">{severity}</span>
        <code>{label}</code>
        <span class="subject">{html.escape(subject)}</span>
      </header>
      <iframe sandbox="" loading="lazy" srcdoc="{srcdoc}"
              onload="this.style.height=this.contentWindow.document.body.scrollHeight+'px'"></iframe>
    </section>"""


def build_gallery() -> str:
    cards = []
    for label, category in _categories():
        severity = effective_severity(category, e.NOTIFICATION_SEVERITY_UNSPECIFIED)
        rendered = render(_demo_event(category))
        body = build_html(rendered, severity).replace(_LOGO_URL, _LOGO_DATA_URI)
        cards.append(
            _card(label, _SEVERITY_NAME.get(severity, "info"), rendered.subject, body)
        )
    return _PAGE.replace("__COUNT__", str(len(cards))).replace("__CARDS__", "\n".join(cards))


_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>LlamaTrade transactional emails — preview</title>
<style>
  body{margin:0;background:#0f172a;color:#e2e8f0;font:14px/1.5 -apple-system,Helvetica,Arial,sans-serif}
  h1{padding:20px 24px;margin:0;font-size:18px;border-bottom:1px solid #1e293b}
  h1 small{color:#64748b;font-weight:400}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(560px,1fr));gap:20px;padding:24px}
  .card{background:#111827;border:1px solid #1e293b;border-radius:10px;overflow:hidden}
  .card header{display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid #1e293b}
  code{color:#93c5fd;font-size:12px}
  .subject{margin-left:auto;color:#94a3b8;font-size:12px}
  .badge{font-size:10px;text-transform:uppercase;letter-spacing:.05em;padding:2px 8px;border-radius:999px;font-weight:700}
  .sev-info .badge{background:#1e3a5f;color:#93c5fd}
  .sev-actionable .badge{background:#3f2d0a;color:#fbbf24}
  .sev-critical .badge{background:#3f1414;color:#f87171}
  .sev-security .badge{background:#3b0a3f;color:#e879f9}
  iframe{width:100%;border:0;background:#fff;display:block;min-height:200px}
</style></head><body>
<h1>Transactional emails <small>&nbsp;· __COUNT__ scenarios · real send path, demo data</small></h1>
<div class="grid">__CARDS__</div>
</body></html>"""


def main() -> None:
    out = Path(__file__).resolve().parent / "email_preview.html"
    out.write_text(build_gallery(), encoding="utf-8")
    print(f"wrote {out}")
    if "--open" in sys.argv:
        subprocess.run(["open", str(out)], check=False)


if __name__ == "__main__":
    main()

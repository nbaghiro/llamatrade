"""HTML email assembly from the committed React Email shells.

The shells in ``email_html/`` are rendered at build time from ``../emails``
(one per severity x cta variant); this module substitutes escaped content into
their placeholders at send time, so all styling lives in the React components
and no Node runtime is needed here.
"""

from __future__ import annotations

import html
import os
from functools import cache
from pathlib import Path

from llamatrade_proto.generated import events_pb2

from src.templates import Rendered

_SHELL_DIR = Path(__file__).parent / "email_html"

_VARIANT_BY_SEVERITY: dict[int, str] = {
    events_pb2.NOTIFICATION_SEVERITY_INFO: "info",
    events_pb2.NOTIFICATION_SEVERITY_ACTIONABLE: "actionable",
    events_pb2.NOTIFICATION_SEVERITY_CRITICAL: "critical",
    events_pb2.NOTIFICATION_SEVERITY_SECURITY: "security",
}


@cache
def _shell(name: str) -> str:
    return (_SHELL_DIR / f"{name}.html").read_text(encoding="utf-8")


def _logo_url() -> str:
    """Absolute URL to the header logo — email clients don't render inline SVG."""
    base = os.getenv("EMAIL_ASSET_BASE_URL", "https://app.llamatrade.ai").rstrip("/")
    return html.escape(f"{base}/logo-monolith.png", quote=True)


def build_html(rendered: Rendered, severity: int) -> str:
    """The final HTML body for one email; placeholders always fully resolve."""
    variant = _VARIANT_BY_SEVERITY.get(severity, "info")
    has_cta = rendered.cta_url is not None
    shell = _shell(f"{variant}_cta" if has_cta else variant)
    out = (
        shell.replace("__LOGO_URL__", _logo_url())
        .replace("__PREHEADER__", html.escape(rendered.message[:120]))
        .replace("__TITLE__", html.escape(rendered.title))
        .replace("__BODY__", html.escape(rendered.message))
    )
    if has_cta:
        out = out.replace("__CTA_URL__", html.escape(rendered.cta_url or "", quote=True))
        out = out.replace("__CTA_LABEL__", html.escape(rendered.cta_label or "Open LlamaTrade"))
    return out

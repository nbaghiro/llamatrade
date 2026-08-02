"""HTML email assembly: variant selection, escaping, CTA handling."""

from __future__ import annotations

import re

import pytest

from llamatrade_proto.generated import events_pb2

from src.email_render import build_html
from src.templates import Rendered, render

_E = events_pb2

SEVERITIES = [
    _E.NOTIFICATION_SEVERITY_INFO,
    _E.NOTIFICATION_SEVERITY_ACTIONABLE,
    _E.NOTIFICATION_SEVERITY_CRITICAL,
    _E.NOTIFICATION_SEVERITY_SECURITY,
]

# Per-severity structural anchors baked into the committed shells: the badge
# label and the accent hex shared by that badge and the bottom keel bar.
_VARIANT_ANCHORS: dict[int, tuple[str, str]] = {
    _E.NOTIFICATION_SEVERITY_INFO: ("Notice", "#0d0d0d"),
    _E.NOTIFICATION_SEVERITY_ACTIONABLE: ("Action needed", "#ff4d1c"),
    _E.NOTIFICATION_SEVERITY_CRITICAL: ("Critical", "#c81e1e"),
    _E.NOTIFICATION_SEVERITY_SECURITY: ("Security", "#24408a"),
}

_PLACEHOLDER = re.compile(r"__[A-Z_]+__")
_ASSET_BASE = "https://assets.test"
_LOGO_SRC = f"{_ASSET_BASE}/logo-monolith.png"


def _representative(*, with_cta: bool) -> Rendered:
    if with_cta:
        return Rendered(
            title="Reset your password",
            message="A password reset was requested for your account.",
            cta_url="https://app.example/reset?token=abc123",
            cta_label="Reset password",
        )
    return Rendered(title="Order filled", message="Your order AAPL filled.")


@pytest.mark.parametrize("severity", SEVERITIES)
def test_every_variant_resolves_all_placeholders(severity: int) -> None:
    html = build_html(Rendered(title="T", message="M"), severity)
    assert "__" not in html
    assert "<html" in html and "LlamaTrade" in html
    assert ">T<" in html or ">T</" in html


def test_severity_tints_differ() -> None:
    rendered = Rendered(title="T", message="M")
    critical = build_html(rendered, _E.NOTIFICATION_SEVERITY_CRITICAL)
    info = build_html(rendered, _E.NOTIFICATION_SEVERITY_INFO)
    assert "#c81e1e" in critical
    assert "#c81e1e" not in info


def test_unknown_severity_falls_back_to_info() -> None:
    assert build_html(Rendered(title="T", message="M"), 99) == build_html(
        Rendered(title="T", message="M"), _E.NOTIFICATION_SEVERITY_INFO
    )


def test_content_is_escaped() -> None:
    html = build_html(
        Rendered(title="<script>alert(1)</script>", message='a & b < c "quoted"'),
        _E.NOTIFICATION_SEVERITY_INFO,
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "a &amp; b &lt; c" in html


def test_cta_variant_renders_button_and_fallback_link() -> None:
    html = build_html(
        Rendered(
            title="Reset your password",
            message="A reset was requested.",
            cta_url="http://localhost:8800/reset-password?token=abc",
            cta_label="Reset password",
        ),
        _E.NOTIFICATION_SEVERITY_SECURITY,
    )
    assert 'href="http://localhost:8800/reset-password?token=abc"' in html
    assert "Reset password" in html
    assert "Or open this link directly" in html
    assert "__" not in html


def test_no_cta_variant_has_no_button() -> None:
    html = build_html(Rendered(title="T", message="M"), _E.NOTIFICATION_SEVERITY_INFO)
    assert "Or open this link directly" not in html


def test_verification_event_link_becomes_cta() -> None:
    event = events_pb2.NotificationEvent(
        category=_E.NOTIFICATION_CATEGORY_EMAIL_VERIFICATION,
        extra={"link": "http://localhost:8800/verify-email?token=xyz"},
    )
    rendered = render(event)
    assert rendered.cta_url == "http://localhost:8800/verify-email?token=xyz"
    assert rendered.cta_label == "Verify email"
    assert "token=" not in rendered.message


def test_reset_event_without_link_keeps_reason_fallback() -> None:
    event = events_pb2.NotificationEvent(
        category=_E.NOTIFICATION_CATEGORY_PASSWORD_RESET,
        reason="Open http://legacy.example/reset",
    )
    rendered = render(event)
    assert rendered.cta_url is None
    assert "legacy.example" in rendered.message


@pytest.mark.parametrize("severity", SEVERITIES)
@pytest.mark.parametrize("with_cta", [False, True])
def test_variant_is_structurally_complete(
    severity: int, with_cta: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Golden structure for each severity x cta shell: logo, copy, keel, no holes."""
    monkeypatch.setenv("EMAIL_ASSET_BASE_URL", _ASSET_BASE)
    rendered = _representative(with_cta=with_cta)
    badge, accent = _VARIANT_ANCHORS[severity]

    out = build_html(rendered, severity)

    # Hosted header logo resolves against the configured asset base.
    assert '<img alt="LlamaTrade"' in out
    assert f'src="{_LOGO_SRC}"' in out

    # Scenario copy is substituted into title and body.
    assert rendered.title in out
    assert rendered.message in out
    if with_cta:
        assert rendered.cta_url is not None and rendered.cta_label is not None
        assert f'href="{rendered.cta_url}"' in out
        assert rendered.cta_label in out

    # Every placeholder resolves — none of the __UPPER__ tokens survive.
    assert _PLACEHOLDER.search(out) is None

    # Structural severity anchors: the badge label and the accent keel bar.
    assert f">{badge}<" in out
    assert f"height:6px;background-color:{accent}" in out


def test_logo_src_follows_asset_base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A trailing slash on the base is trimmed before the logo path is joined."""
    monkeypatch.setenv("EMAIL_ASSET_BASE_URL", "https://cdn.example.com/brand/")
    out = build_html(Rendered(title="T", message="M"), _E.NOTIFICATION_SEVERITY_INFO)
    assert 'src="https://cdn.example.com/brand/logo-monolith.png"' in out

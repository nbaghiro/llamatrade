"""Category routing: defaults, preference narrowing, severity pinning."""

from __future__ import annotations

from llamatrade_proto.generated import events_pb2, notification_pb2

from src.preferences import (
    CATEGORY_SPECS,
    EMAIL,
    PINNED_SEVERITIES,
    WEBHOOK,
    channels_for,
    effective_severity,
    spec_for,
)

_E = events_pb2


class TestSpecs:
    def test_every_declared_category_has_a_spec(self) -> None:
        declared = {
            v
            for v in events_pb2.NotificationCategory.values()
            if v != _E.NOTIFICATION_CATEGORY_UNSPECIFIED
        }
        assert declared == set(CATEGORY_SPECS)

    def test_unknown_category_falls_back(self) -> None:
        spec = spec_for(9999)
        assert spec.channels == frozenset()
        assert spec.notification_type == notification_pb2.NOTIFICATION_TYPE_SYSTEM

    def test_pinned_severities(self) -> None:
        assert PINNED_SEVERITIES == {
            _E.NOTIFICATION_SEVERITY_CRITICAL,
            _E.NOTIFICATION_SEVERITY_SECURITY,
        }


class TestEffectiveSeverity:
    def test_event_severity_wins(self) -> None:
        assert (
            effective_severity(
                _E.NOTIFICATION_CATEGORY_ORDER_FILLED, _E.NOTIFICATION_SEVERITY_CRITICAL
            )
            == _E.NOTIFICATION_SEVERITY_CRITICAL
        )

    def test_default_when_unset(self) -> None:
        assert (
            effective_severity(_E.NOTIFICATION_CATEGORY_SLEEVE_FROZEN, 0)
            == _E.NOTIFICATION_SEVERITY_CRITICAL
        )


class TestChannelsFor:
    def test_defaults_without_prefs(self) -> None:
        targets = channels_for(
            _E.NOTIFICATION_CATEGORY_POSITION_DRIFT, _E.NOTIFICATION_SEVERITY_ACTIONABLE, {}
        )
        assert targets == {EMAIL, WEBHOOK}

    def test_disabled_channel_drops(self) -> None:
        targets = channels_for(
            _E.NOTIFICATION_CATEGORY_POSITION_DRIFT,
            _E.NOTIFICATION_SEVERITY_ACTIONABLE,
            {EMAIL: None},
        )
        assert targets == {WEBHOOK}

    def test_category_matrix_narrows(self) -> None:
        prefs = {EMAIL: {"categories": [int(_E.NOTIFICATION_CATEGORY_PAYMENT_FAILED)]}}
        targets = channels_for(
            _E.NOTIFICATION_CATEGORY_POSITION_DRIFT,
            _E.NOTIFICATION_SEVERITY_ACTIONABLE,
            prefs,
        )
        assert targets == {WEBHOOK}

    def test_matrix_keeps_listed_category(self) -> None:
        prefs = {EMAIL: {"categories": [int(_E.NOTIFICATION_CATEGORY_POSITION_DRIFT)]}}
        targets = channels_for(
            _E.NOTIFICATION_CATEGORY_POSITION_DRIFT,
            _E.NOTIFICATION_SEVERITY_ACTIONABLE,
            prefs,
        )
        assert EMAIL in targets

    def test_critical_pins_email_over_optout(self) -> None:
        targets = channels_for(
            _E.NOTIFICATION_CATEGORY_SLEEVE_FROZEN,
            _E.NOTIFICATION_SEVERITY_CRITICAL,
            {EMAIL: None},
        )
        assert EMAIL in targets

    def test_security_pins_email_over_matrix(self) -> None:
        prefs = {EMAIL: {"categories": [int(_E.NOTIFICATION_CATEGORY_ORDER_FILLED)]}}
        targets = channels_for(
            _E.NOTIFICATION_CATEGORY_PASSWORD_CHANGED,
            _E.NOTIFICATION_SEVERITY_SECURITY,
            prefs,
        )
        assert EMAIL in targets

    def test_info_respects_optout(self) -> None:
        targets = channels_for(
            _E.NOTIFICATION_CATEGORY_PAYMENT_SUCCEEDED,
            _E.NOTIFICATION_SEVERITY_INFO,
            {EMAIL: None},
        )
        assert targets == frozenset()

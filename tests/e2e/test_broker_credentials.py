"""E2E: broker credential lifecycle — Create, Get, List, Delete over the wire.

Proves the encrypt-store-mask loop (the secret is write-only; reads return an
8-char key prefix) and the deletion guard: while a funded, non-closed sleeve
depends on the credential, DeleteAlpacaCredentials fails with
``failed_precondition``; once the execution is stopped and the sleeve closed,
the delete succeeds. Placeholder keys are stored unvalidated — the live broker
check is the separate ValidateAlpacaCredentials RPC (covered in
test_auth_onboarding), which the UI calls before saving.

All of it runs on throwaway tenants; the credential RPCs authenticate on the
JWT alone (NO_CONTEXT methods).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from . import _ledger, _scaffold
from .client import MeshClient, MeshError

pytestmark = pytest.mark.e2e


def test_credential_lifecycle_masks_and_soft_deletes(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("cred")

    created = client.call(
        "auth",
        "CreateAlpacaCredentials",
        {
            "name": "e2e paper keys",
            "apiKey": _scaffold.PLACEHOLDER_KEY,
            "apiSecret": _scaffold.PLACEHOLDER_SECRET,
            "isPaper": True,
        },
    )["credentials"]
    assert created["id"]
    assert created["name"] == "e2e paper keys"
    assert created["isPaper"] is True
    assert created["isActive"] is True
    # Write-only: the response carries a masked 8-char prefix and no secret.
    assert created.get("apiKey") == f"{_scaffold.PLACEHOLDER_KEY[:8]}…"
    assert not created.get("apiSecret")

    got = client.call("auth", "GetAlpacaCredentials", {"credentialsId": created["id"]})[
        "credentials"
    ]
    assert got.get("apiKey") == f"{_scaffold.PLACEHOLDER_KEY[:8]}…"
    assert not got.get("apiSecret")

    listed = client.call("auth", "ListAlpacaCredentials", {}).get("credentials", [])
    assert [c["id"] for c in listed] == [created["id"]]
    assert listed[0].get("apiKeyPrefix") == _scaffold.PLACEHOLDER_KEY[:8]

    deleted = client.call("auth", "DeleteAlpacaCredentials", {"credentialsId": created["id"]})
    assert deleted.get("success") is True

    # Soft delete: the row disappears from list and Get resolves not_found.
    assert client.call("auth", "ListAlpacaCredentials", {}).get("credentials", []) == []
    with pytest.raises(MeshError) as excinfo:
        client.call("auth", "GetAlpacaCredentials", {"credentialsId": created["id"]})
    assert excinfo.value.code == "not_found"


def test_create_rejects_an_undersized_secret_as_invalid_argument(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    # Regression: an input failing model validation must map to invalid_argument,
    # not surface as an internal error.
    client = throwaway_tenant("cred-bad")
    with pytest.raises(MeshError) as excinfo:
        client.call(
            "auth",
            "CreateAlpacaCredentials",
            {
                "name": "too short",
                "apiKey": _scaffold.PLACEHOLDER_KEY,
                "apiSecret": "way-too-short",
                "isPaper": True,
            },
        )
    assert excinfo.value.code == "invalid_argument"
    assert client.call("auth", "ListAlpacaCredentials", {}).get("credentials", []) == []


def test_delete_is_blocked_while_a_funded_sleeve_depends_on_it(
    demo: MeshClient, throwaway_tenant: Callable[[str], MeshClient]
) -> None:
    client = throwaway_tenant("cred-dep")
    funded = _scaffold.fund_tenant_execution(client, demo, "E2E cred dependent")

    stopped = False
    try:
        with pytest.raises(MeshError) as excinfo:
            client.call("auth", "DeleteAlpacaCredentials", {"credentialsId": funded.credentials_id})
        assert excinfo.value.code == "failed_precondition"
        assert "in use" in excinfo.value.message

        client.call(
            "strategy",
            "StopExecution",
            {"executionId": funded.execution_id, "reason": "e2e release dependents"},
        )
        stopped = True
        assert _ledger.wait_sleeve_closed(client, funded.account_id, funded.sleeve_id)

        deleted = client.call(
            "auth", "DeleteAlpacaCredentials", {"credentialsId": funded.credentials_id}
        )
        assert deleted.get("success") is True
    finally:
        if not stopped:
            client.try_call(
                "strategy",
                "StopExecution",
                {"executionId": funded.execution_id, "reason": "e2e failed run"},
            )

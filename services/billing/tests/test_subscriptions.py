"""Tests for subscription endpoints."""

from httpx import AsyncClient

from tests.conftest import (
    make_auth_header,
)


class TestListPlans:
    """Tests for GET /subscriptions/plans."""

    async def test_list_plans_returns_default_plans(self, client: AsyncClient) -> None:
        """Test listing plans returns default plans."""
        response = await client.get("/subscriptions/plans")

        assert response.status_code == 200
        plans = response.json()
        assert len(plans) >= 3

        # Check that we have free, starter, and pro
        tiers = [p["tier"] for p in plans]
        assert "free" in tiers
        assert "starter" in tiers
        assert "pro" in tiers

    async def test_free_plan_has_zero_price(self, client: AsyncClient) -> None:
        """Test that the free plan has zero price."""
        response = await client.get("/subscriptions/plans")

        assert response.status_code == 200
        plans = response.json()
        free_plan = next((p for p in plans if p["tier"] == "free"), None)

        assert free_plan is not None
        assert free_plan["price_monthly"] == 0
        assert free_plan["price_yearly"] == 0

    async def test_paid_plans_have_trial_days(self, client: AsyncClient) -> None:
        """Test that paid plans have trial days."""
        response = await client.get("/subscriptions/plans")

        assert response.status_code == 200
        plans = response.json()

        for plan in plans:
            if plan["tier"] in ["starter", "pro"]:
                assert plan["trial_days"] > 0


class TestGetPlanById:
    """Tests for GET /subscriptions/plans/{plan_id}."""

    async def test_get_plan_returns_plan(self, client: AsyncClient) -> None:
        """Test getting a specific plan by ID."""
        response = await client.get("/subscriptions/plans/starter")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "starter"
        assert data["tier"] == "starter"
        assert data["price_monthly"] == 29

    async def test_get_plan_not_found(self, client: AsyncClient) -> None:
        """Test getting non-existent plan returns 404."""
        response = await client.get("/subscriptions/plans/nonexistent")

        assert response.status_code == 404

    async def test_get_free_plan(self, client: AsyncClient) -> None:
        """Test getting the free plan."""
        response = await client.get("/subscriptions/plans/free")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "free"
        assert data["price_monthly"] == 0

    async def test_get_pro_plan(self, client: AsyncClient) -> None:
        """Test getting the pro plan."""
        response = await client.get("/subscriptions/plans/pro")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "pro"
        assert data["price_monthly"] == 99


class TestGetCurrentSubscription:
    """Tests for GET /subscriptions/current."""

    async def test_get_subscription_requires_auth(self, client: AsyncClient) -> None:
        """Test that getting subscription requires authentication."""
        response = await client.get("/subscriptions/current")

        assert response.status_code == 401

    async def test_get_subscription_returns_null_when_none(self, client: AsyncClient) -> None:
        """Test getting subscription when tenant has none."""
        headers = make_auth_header()
        response = await client.get("/subscriptions/current", headers=headers)

        assert response.status_code == 200
        # Response can be null/None
        assert response.json() is None or response.json() == {}

    async def test_get_subscription_returns_subscription_when_exists(
        self, client_with_subscription: AsyncClient
    ) -> None:
        """Test getting subscription when tenant has one."""
        headers = make_auth_header()
        response = await client_with_subscription.get("/subscriptions/current", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data is not None
        assert data["status"] == "active"
        assert "plan" in data


class TestCreateSubscription:
    """Tests for POST /subscriptions."""

    async def test_create_subscription_requires_auth(self, client: AsyncClient) -> None:
        """Test that creating subscription requires authentication."""
        response = await client.post(
            "/subscriptions",
            json={
                "plan_id": "starter",
                "payment_method_id": "pm_test",
                "billing_cycle": "monthly",
            },
        )

        assert response.status_code == 401

    async def test_create_subscription_validation_error(self, client: AsyncClient) -> None:
        """Test validation error for invalid request."""
        headers = make_auth_header()
        response = await client.post(
            "/subscriptions",
            headers=headers,
            json={
                "plan_id": "",  # Invalid - empty plan_id
                "payment_method_id": "pm_test",
            },
        )

        # Should fail validation or plan not found
        assert response.status_code in [400, 422]


class TestUpdateSubscription:
    """Tests for PUT /subscriptions."""

    async def test_update_subscription_requires_auth(self, client: AsyncClient) -> None:
        """Test that updating subscription requires authentication."""
        response = await client.put(
            "/subscriptions",
            json={"plan_id": "pro"},
        )

        assert response.status_code == 401

    async def test_update_subscription_no_active_subscription(self, client: AsyncClient) -> None:
        """Test updating when no subscription exists."""
        headers = make_auth_header()
        response = await client.put(
            "/subscriptions",
            headers=headers,
            json={"plan_id": "pro"},
        )

        assert response.status_code == 400


class TestCancelSubscription:
    """Tests for POST /subscriptions/cancel."""

    async def test_cancel_subscription_requires_auth(self, client: AsyncClient) -> None:
        """Test that canceling subscription requires authentication."""
        response = await client.post(
            "/subscriptions/cancel",
            json={"at_period_end": True},
        )

        assert response.status_code == 401

    async def test_cancel_subscription_no_active_subscription(self, client: AsyncClient) -> None:
        """Test canceling when no subscription exists."""
        headers = make_auth_header()
        response = await client.post(
            "/subscriptions/cancel",
            headers=headers,
            json={"at_period_end": True},
        )

        assert response.status_code == 400

    async def test_cancel_subscription_success(self, client_with_subscription: AsyncClient) -> None:
        """Test successful subscription cancellation."""
        headers = make_auth_header()
        response = await client_with_subscription.post(
            "/subscriptions/cancel",
            headers=headers,
            json={"at_period_end": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["cancel_at_period_end"] is True


class TestReactivateSubscription:
    """Tests for POST /subscriptions/reactivate."""

    async def test_reactivate_subscription_requires_auth(self, client: AsyncClient) -> None:
        """Test that reactivating subscription requires authentication."""
        response = await client.post("/subscriptions/reactivate")

        assert response.status_code == 401

    async def test_reactivate_subscription_no_cancelled(self, client: AsyncClient) -> None:
        """Test reactivating when no cancelled subscription exists."""
        headers = make_auth_header()
        response = await client.post("/subscriptions/reactivate", headers=headers)

        assert response.status_code == 400

    async def test_reactivate_subscription_success(
        self, client_with_cancelled_subscription: AsyncClient
    ) -> None:
        """Test successful subscription reactivation."""
        headers = make_auth_header()
        response = await client_with_cancelled_subscription.post(
            "/subscriptions/reactivate",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["cancel_at_period_end"] is False


class TestListInvoices:
    """Tests for GET /subscriptions/invoices."""

    async def test_list_invoices_requires_auth(self, client: AsyncClient) -> None:
        """Test that listing invoices requires authentication."""
        response = await client.get("/subscriptions/invoices")

        assert response.status_code == 401

    async def test_list_invoices_returns_empty_without_subscription(
        self, client: AsyncClient
    ) -> None:
        """Test listing invoices without subscription returns empty list."""
        headers = make_auth_header()
        response = await client.get("/subscriptions/invoices", headers=headers)

        assert response.status_code == 200
        assert response.json() == []

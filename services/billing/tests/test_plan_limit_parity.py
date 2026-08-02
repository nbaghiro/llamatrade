"""The free catalog plan and the no-subscription fallback must agree on limits."""

from llamatrade_db.plan_limits import FREE_TIER_LIMITS

from src.services.billing_service import DEFAULT_PLANS


def test_free_plan_limits_match_fallback() -> None:
    free = next(p for p in DEFAULT_PLANS if p.name == "free")
    for key, value in FREE_TIER_LIMITS.items():
        assert free.limits[key] == value, f"catalog free plan diverges from fallback on {key}"


def test_fallback_keys_all_present_in_catalog() -> None:
    free = next(p for p in DEFAULT_PLANS if p.name == "free")
    assert set(FREE_TIER_LIMITS) <= set(free.limits)

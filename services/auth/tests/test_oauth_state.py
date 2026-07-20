"""Signed OAuth state mint/verify."""

import jwt

from src.oauth_state import mint_state, verify_state


def test_mint_and_verify_link_state() -> None:
    tok = mint_state("link", tenant_id="t1", user_id="u1", secret="s")
    st = verify_state(tok, secret="s")
    assert st is not None
    assert st.intent == "link"
    assert st.tenant_id == "t1"
    assert st.user_id == "u1"
    assert st.nonce


def test_verify_rejects_bad_signature() -> None:
    tok = mint_state("auth", secret="s1")
    assert verify_state(tok, secret="s2") is None


def test_verify_rejects_expired() -> None:
    tok = mint_state("link", secret="s", ttl_seconds=-1)
    assert verify_state(tok, secret="s") is None


def test_verify_rejects_wrong_purpose() -> None:
    tok = jwt.encode({"purpose": "other", "intent": "link", "exp": 9999999999}, "s", algorithm="HS256")
    assert verify_state(tok, secret="s") is None


def test_verify_rejects_unknown_intent() -> None:
    tok = jwt.encode(
        {"purpose": "alpaca_oauth_state", "intent": "bogus", "exp": 9999999999}, "s", algorithm="HS256"
    )
    assert verify_state(tok, secret="s") is None

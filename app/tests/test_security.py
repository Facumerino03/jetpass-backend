from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    get_password_hash,
    hash_refresh_token,
    verify_password,
)


def test_password_hash_verification():
    password_hash = get_password_hash("safe-password")

    assert password_hash != "safe-password"
    assert verify_password("safe-password", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_access_token_contains_expected_claims():
    token = create_access_token(
        subject="user-123",
        role="pilot",
        expires_delta=timedelta(minutes=5),
    )

    payload = decode_access_token(token)

    assert payload["sub"] == "user-123"
    assert payload["role"] == "pilot"
    assert payload["type"] == "access"


def test_decode_rejects_non_access_token():
    token = create_access_token(
        subject="user-123",
        role="pilot",
        expires_delta=timedelta(minutes=5),
        token_type="refresh",
    )

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)

    assert exc_info.value.status_code == 401


def test_refresh_token_is_opaque_and_hashable():
    token = generate_refresh_token()
    token_hash = hash_refresh_token(token)

    assert len(token) >= 43
    assert token_hash != token
    assert hash_refresh_token(token) == token_hash

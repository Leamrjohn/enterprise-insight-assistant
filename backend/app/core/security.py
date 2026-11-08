"""Secrets used by the platform authentication boundary."""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_password_hasher = PasswordHasher()


def hash_api_key(api_key: str) -> str:
    """Return the database representation of a high-entropy API key."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    """Generate an API key that is shown to the caller exactly once."""
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    """Hash a password with Argon2; plaintext is never persisted."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False

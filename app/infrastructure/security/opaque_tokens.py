"""Helpers for opaque token generation and hashing."""

from __future__ import annotations

import hashlib
import secrets


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

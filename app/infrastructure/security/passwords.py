"""Password hashing helpers."""

from __future__ import annotations

import hashlib
import secrets
from hmac import compare_digest

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_hex(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    )
    return f"{PASSWORD_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, encoded_password: str) -> bool:
    algorithm, iterations, salt, expected_digest = encoded_password.split("$", maxsplit=3)
    if algorithm != PASSWORD_ALGORITHM:
        return False

    computed_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        int(iterations),
    ).hex()
    return compare_digest(computed_digest, expected_digest)

"""Password hashing (Argon2) and JWT token creation/verification."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

_hasher = PasswordHasher()

ACCESS_TOKEN = "access"
REFRESH_TOKEN = "refresh"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except (InvalidHashError, ValueError):
        return True


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    expire = _now() + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": ACCESS_TOKEN,
        "exp": expire,
        "iat": _now(),
        "jti": str(uuid.uuid4()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> tuple[str, str, datetime]:
    """Return ``(token, token_hash, expires_at)``.

    Only the hash is persisted so a database leak cannot reveal usable tokens.
    """
    expire = _now() + timedelta(days=settings.refresh_token_expire_days)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(subject),
        "type": REFRESH_TOKEN,
        "exp": expire,
        "iat": _now(),
        "jti": jti,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, hash_token(token), expire


def hash_token(token: str) -> str:
    """Deterministic hash used to store/lookup refresh tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises ``jwt.PyJWTError`` on failure."""
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )

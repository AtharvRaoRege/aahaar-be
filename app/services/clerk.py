"""Verify Clerk session JWTs and load the Clerk user profile."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import settings
from app.core.errors import AppError, UnauthorizedError


class ClerkNotConfiguredError(AppError):
    status_code = 503
    code = "CLERK_NOT_CONFIGURED"
    message = "Google login is not configured. Add CLERK_SECRET_KEY (see clerk.md)."


@dataclass(frozen=True)
class ClerkProfile:
    clerk_user_id: str
    email: str
    full_name: str


@lru_cache(maxsize=8)
def _jwks_client(issuer: str) -> PyJWKClient:
    return PyJWKClient(f"{issuer.rstrip('/')}/.well-known/jwks.json")


def verify_clerk_session_token(token: str) -> str:
    """Return the Clerk user id (`sub`) from a valid session JWT."""
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid Clerk token.", code="INVALID_TOKEN") from exc

    issuer = str(unverified.get("iss") or "")
    if "clerk" not in issuer.lower():
        raise UnauthorizedError("Invalid Clerk token.", code="INVALID_TOKEN")

    try:
        key = _jwks_client(issuer).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            issuer=issuer,
            leeway=10,
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired Clerk token.", code="INVALID_TOKEN") from exc

    parties = settings.clerk_authorized_parties
    azp = payload.get("azp")
    if parties and azp and azp not in parties:
        raise UnauthorizedError("Clerk token origin is not allowed.", code="INVALID_TOKEN")

    subject = payload.get("sub")
    if not subject:
        raise UnauthorizedError("Invalid Clerk token subject.", code="INVALID_TOKEN")
    return str(subject)


async def fetch_clerk_profile(clerk_user_id: str) -> ClerkProfile:
    if not settings.clerk_enabled:
        raise ClerkNotConfiguredError()

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
        )
    if response.status_code == 404:
        raise UnauthorizedError("Clerk user was not found.", code="INVALID_TOKEN")
    if response.status_code >= 400:
        raise UnauthorizedError("Could not load the Google account.", code="CLERK_USER_FETCH")

    data = response.json()
    emails = data.get("email_addresses") or []
    primary_id = data.get("primary_email_address_id")
    email = ""
    for entry in emails:
        if entry.get("id") == primary_id or not email:
            email = str(entry.get("email_address") or "")
    if not email:
        raise UnauthorizedError("Google account has no email address.", code="CLERK_EMAIL_MISSING")

    first = str(data.get("first_name") or "").strip()
    last = str(data.get("last_name") or "").strip()
    full_name = " ".join(part for part in (first, last) if part) or email.split("@")[0]
    return ClerkProfile(
        clerk_user_id=clerk_user_id,
        email=email.lower(),
        full_name=full_name[:120],
    )

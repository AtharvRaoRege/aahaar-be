"""VAPID key material for Web Push.

If ``VAPID_PRIVATE_KEY`` is unset, keys are derived from ``SECRET_KEY`` so local
and production stay stable across restarts without extra env files.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

_SECP256R1_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def _private_key() -> ec.EllipticCurvePrivateKey:
    pem = settings.vapid_private_key.strip()
    if pem:
        loaded = serialization.load_pem_private_key(pem.encode(), password=None)
        if not isinstance(loaded, ec.EllipticCurvePrivateKey):
            raise ValueError("VAPID_PRIVATE_KEY must be an EC P-256 PEM key.")
        return loaded
    material = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"aahaar-vapid-v1",
        info=b"web-push",
    ).derive(settings.secret_key.encode())
    value = int.from_bytes(material, "big") % (_SECP256R1_ORDER - 1) + 1
    return ec.derive_private_key(value, ec.SECP256R1())


def vapid_private_pem() -> str:
    key = _private_key()
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def vapid_public_key() -> str:
    raw = (
        _private_key()
        .public_key()
        .public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
    )
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def vapid_claims() -> dict[str, str]:
    contact = settings.vapid_contact.strip() or "mailto:hello@aahaar.app"
    if not contact.startswith(("mailto:", "https://")):
        contact = f"mailto:{contact}"
    return {"sub": contact}

"""
Symmetric encryption at rest for OAuth tokens (spec section 29: "encrypted
secrets"). The Fernet key is derived deterministically from SECRET_KEY --
rotating SECRET_KEY invalidates stored tokens, which is the correct
behavior (that key is also what signs owner auth sessions, so a rotation
already implies "re-authenticate everything").
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")

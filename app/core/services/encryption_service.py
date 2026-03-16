"""
AES-256-GCM encryption for platform OAuth tokens and API keys.
Stores: nonce (12 bytes) + ciphertext + auth_tag (16 bytes) as a single blob.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


class EncryptionService:
    """Encrypt / decrypt sensitive credentials using AES-256-GCM."""

    def __init__(self):
        key_bytes = base64.b64decode(settings.encryption_key)
        if len(key_bytes) != 32:
            raise ValueError("ENCRYPTION_KEY must decode to exactly 32 bytes")
        self._aesgcm = AESGCM(key_bytes)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a string → bytes (nonce + ciphertext+tag)."""
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode(), None)
        return nonce + ciphertext  # 12 + len(plaintext) + 16

    def decrypt(self, blob: bytes) -> str:
        """Decrypt bytes (nonce + ciphertext+tag) → string."""
        nonce = blob[:12]
        ciphertext = blob[12:]
        plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode()

encryption = EncryptionService()

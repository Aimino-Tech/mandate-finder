from __future__ import annotations

import hashlib
import os
from base64 import b64decode, b64encode
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.config import settings

AAD = b"mandate-finder-v1"
PII_FIELDS = {"email", "phone", "name", "linkedin_url", "first_name", "last_name"}
KEY_FILE = Path(settings.app_data_dir) / "encryption_key.bin"


def _load_or_create_key() -> bytes:
    raw = os.environ.get("MF_ENCRYPTION_KEY")
    if raw:
        return b64decode(raw)
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    key = AESGCM.generate_key(bit_length=256)
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_bytes(key)
    KEY_FILE.chmod(0o600)
    return key


_encryption_key: bytes | None = None


def _ensure_key() -> bytes:
    global _encryption_key
    if _encryption_key is None:
        _encryption_key = _load_or_create_key()
    return _encryption_key


def get_encryption_key_info() -> dict:
    return {
        "algorithm": "AES-256-GCM",
        "key_source": "MF_ENCRYPTION_KEY env var" if os.environ.get("MF_ENCRYPTION_KEY") else f"file: {KEY_FILE}",
        "key_rotation_supported": True,
        "fields_encrypted": sorted(PII_FIELDS),
        "aad_context": AAD.decode(),
    }


def rotate_encryption_key(new_key_b64: str | None = None) -> dict:
    old_key = _ensure_key()
    new_key = b64decode(new_key_b64) if new_key_b64 else AESGCM.generate_key(bit_length=256)
    global _encryption_key
    _encryption_key = new_key
    KEY_FILE.write_bytes(new_key)
    KEY_FILE.chmod(0o600)
    return {
        "status": "rotated",
        "previous_key_hash": hashlib.sha256(old_key).hexdigest()[:16],
        "new_key_hash": hashlib.sha256(new_key).hexdigest()[:16],
        "note": "Existing encrypted data must be re-encrypted with the new key.",
    }


def encrypt_field(plaintext: str) -> str:
    if not plaintext:
        return ""
    key = _ensure_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), AAD)
    return b64encode(nonce + ciphertext).decode("ascii")


def decrypt_field(ciphertext_b64: str) -> str:
    if not ciphertext_b64:
        return ""
    key = _ensure_key()
    data = b64decode(ciphertext_b64)
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, AAD)
    return plaintext.decode("utf-8")


def mask_field(value: str, visible_chars: int = 2) -> str:
    if not value:
        return ""
    if len(value) <= visible_chars:
        return value
    return value[:visible_chars] + "*" * (len(value) - visible_chars)


def is_pii_field(field_name: str) -> bool:
    return field_name.lower() in PII_FIELDS

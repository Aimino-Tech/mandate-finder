import hashlib
import hmac
import secrets

from src.config import settings


def generate_api_key() -> tuple[str, str]:
    raw = secrets.token_hex(settings.api_key_bytes)
    key = f"{settings.api_key_prefix}{raw}"
    return key, hash_api_key(key)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(key: str, key_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(key), key_hash)


def generate_webhook_secret() -> str:
    return secrets.token_hex(32)

"""Encryption utilities for credential storage."""

import base64
import os
from pathlib import Path

_DATA_DIR = Path.home() / ".iflycode-proxy"
_KEY_FILE = _DATA_DIR / ".enc_key"

_PREFIX = "enc:"


def _get_key() -> bytes:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _KEY_FILE.exists():
        return base64.urlsafe_b64decode(_KEY_FILE.read_text().strip())
    key = os.urandom(32)
    _KEY_FILE.write_text(base64.urlsafe_b64encode(key).decode())
    _KEY_FILE.chmod(0o600)
    return key


def encrypt(plaintext: str) -> str:
    from cryptography.fernet import Fernet
    key = _get_key()
    f = Fernet(base64.urlsafe_b64encode(key))
    return _PREFIX + f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    from cryptography.fernet import Fernet
    key = _get_key()
    f = Fernet(base64.urlsafe_b64encode(key))
    return f.decrypt(ciphertext[len(_PREFIX):].encode()).decode()


def is_encrypted(value: str) -> bool:
    return value.startswith(_PREFIX)

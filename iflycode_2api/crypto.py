"""Encryption utilities for credential storage.

Uses AES-256-GCM directly. Storage format:  aes:<hex(nonce + ciphertext + tag)>

Legacy Fernet-encrypted values (enc: prefix) are still supported for decryption.
The key file (~/.iflycode-2api/.enc_key) stores raw 32-byte key as hex.
"""

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_DATA_DIR = Path.home() / ".iflycode-2api"
_KEY_FILE = _DATA_DIR / ".enc_key"
_LEGACY_KEY_FILE = _DATA_DIR / ".enc_key.legacy"

_AES_PREFIX = "aes:"
_FERNET_PREFIX = "enc:"


def _get_key() -> bytes:
    """Load or create a 32-byte AES key, stored as hex."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _KEY_FILE.exists():
        raw = _KEY_FILE.read_text().strip()
        # Try hex first (new format), fallback to base64 (legacy format)
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
        # Legacy: key file was base64-encoded raw key
        return base64.urlsafe_b64decode(raw)
    key = AESGCM.generate_key(bit_length=256)
    _KEY_FILE.write_text(key.hex())
    _KEY_FILE.chmod(0o600)
    return key


def encrypt(plaintext: str) -> str:
    """Encrypt using AES-256-GCM. Returns 'aes:' + hex(nonce + ct + tag).

    The AEAD interface produces ciphertext with the 16-byte GCM tag appended,
    so a single hex blob stores nonce (12) + ct (variable) + tag (16).
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return _AES_PREFIX + (nonce + ct).hex()


def decrypt(ciphertext: str) -> str:
    """Decrypt a value. Handles both 'aes:' (current) and 'enc:' (legacy Fernet) prefixes."""
    if ciphertext.startswith(_FERNET_PREFIX):
        return _decrypt_fernet(ciphertext)
    if not ciphertext.startswith(_AES_PREFIX):
        raise ValueError(f"Unknown encryption prefix in: {ciphertext[:12]!r}")
    return _decrypt_aes(ciphertext)


def _decrypt_aes(ciphertext: str) -> str:
    key = _get_key()
    raw = bytes.fromhex(ciphertext[len(_AES_PREFIX):])
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode()


def _decrypt_fernet(ciphertext: str) -> str:
    """Decrypt legacy Fernet-encrypted value using the raw key."""
    from cryptography.fernet import Fernet
    key = _get_key()
    # Fernet key needs to be base64-urlsafe-encoded 32 bytes
    fernet_key = base64.urlsafe_b64encode(key)
    f = Fernet(fernet_key)
    return f.decrypt(ciphertext[len(_FERNET_PREFIX):].encode()).decode()


def is_encrypted(value: str) -> bool:
    return value.startswith(_AES_PREFIX) or value.startswith(_FERNET_PREFIX)
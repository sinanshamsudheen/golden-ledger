"""
Fernet symmetric encryption for sensitive values stored in the database
(primarily Google OAuth refresh tokens).

Key management
--------------
Set ENCRYPTION_KEY in .env to a Fernet key generated with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

The key is 32 cryptographically random bytes encoded as URL-safe base64 (44 chars).
Keep it secret — rotating it requires re-encrypting all stored tokens.

Migration safety
----------------
decrypt() falls back to returning the ciphertext as-is when it cannot be
decrypted.  This lets existing plaintext tokens keep working until the user
re-authenticates and their token is stored encrypted.
"""

from cryptography.fernet import Fernet, InvalidToken

from ..config import settings


def _fernet() -> Fernet:
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return the Fernet ciphertext as a UTF-8 string."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """
    Decrypt a Fernet ciphertext.

    Falls back to returning ``ciphertext`` unchanged if decryption fails —
    this handles the one-time migration window where tokens were stored
    as plaintext before encryption was introduced.
    """
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return ciphertext

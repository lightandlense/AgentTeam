import pytest
from cryptography.fernet import Fernet

from app.services.encryption import (
    InvalidToken,
    decrypt_token,
    encrypt_token,
    generate_key,
)


def test_encrypt_produces_ciphertext_not_equal_to_plaintext() -> None:
    """Encrypted output must not equal the original plaintext."""
    key = generate_key()
    plaintext = "test-token-value"
    result = encrypt_token(plaintext, key)
    assert result != plaintext
    assert isinstance(result, str)
    assert len(result) > 0


def test_decrypt_recovers_original() -> None:
    """Decrypting ciphertext with the same key must return the original plaintext."""
    key = generate_key()
    original = "ya29.google-oauth-access-token"
    ciphertext = encrypt_token(original, key)
    recovered = decrypt_token(ciphertext, key)
    assert recovered == original


def test_wrong_key_raises_invalid_token() -> None:
    """Decrypting with a different key must raise InvalidToken."""
    key_a = generate_key()
    key_b = generate_key()
    ciphertext = encrypt_token("secret-value", key_a)
    with pytest.raises(InvalidToken):
        decrypt_token(ciphertext, key_b)


def test_generate_key_returns_valid_fernet_key() -> None:
    """generate_key() must return a 44-character URL-safe base64 Fernet key."""
    key = generate_key()
    # Constructing a Fernet instance validates the key format
    Fernet(key.encode())
    assert len(key) == 44

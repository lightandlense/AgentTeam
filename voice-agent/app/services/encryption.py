from cryptography.fernet import Fernet, InvalidToken


def generate_key() -> str:
    """Generate a new Fernet key. Run once and store in ENCRYPTION_KEY env var."""
    return Fernet.generate_key().decode()


def encrypt_token(plaintext: str, key: str) -> str:
    """Encrypt a plaintext token string. Returns URL-safe base64 ciphertext string."""
    f = Fernet(key.encode())
    return f.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str, key: str) -> str:
    """Decrypt a ciphertext token string. Raises InvalidToken if key is wrong or data is tampered."""
    f = Fernet(key.encode())
    return f.decrypt(ciphertext.encode()).decode()


__all__ = ["generate_key", "encrypt_token", "decrypt_token", "InvalidToken"]

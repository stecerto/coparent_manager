# core/encryption.py   GESTIONE CHIAVI
import os

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured


def get_encryption_key():
    # 1️⃣ Legge e pulisce da spazi/virgolette accidentali
    key = os.environ.get("ENCRYPTION_KEY", "").strip().strip("'\"b ")

    if not key or len(key) < 40:
        raise ImproperlyConfigured(
            "❌ ENCRYPTION_KEY non valida. "
            "Generala ESATTAMENTE così: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )

    # 2️⃣ Fernet accetta la stringa base64 codificata in bytes
    return key.encode('utf-8')


# ✅ Inizializza UNA sola volta (thread-safe)
fernet = Fernet(get_encryption_key())


def encrypt_bytes(data: bytes) -> bytes:
    return fernet.encrypt(data) if data else b""


def decrypt_bytes(token: bytes) -> bytes:
    return fernet.decrypt(token) if token else b""


def encrypt_text(text: str) -> str:
    return encrypt_bytes(text.encode("utf-8")).decode("utf-8") if text else ""


def decrypt_text(token: str) -> str:
    return decrypt_bytes(token.encode("utf-8")).decode("utf-8") if token else ""
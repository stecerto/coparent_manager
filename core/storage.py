# core/storage.py  FILE CRIPTATI
from django.core.files.storage import FileSystemStorage
from .encryption import encrypt_bytes, decrypt_bytes


class EncryptedFileSystemStorage(FileSystemStorage):
    """Salva file criptati su disco. Legge e decripta on-the-fly."""

    def _save(self, name, content):
        # Leggi contenuto, cripta, salva
        content_bytes = content.read()
        encrypted = encrypt_bytes(content_bytes)
        content.seek(0)
        content.write(encrypted)
        content.seek(0)
        return super()._save(name, content)

    def _open(self, name, mode="rb"):
        file = super()._open(name, mode)
        encrypted = file.read()
        file.close()
        decrypted = decrypt_bytes(encrypted)
        from django.core.files.base import ContentFile
        return ContentFile(decrypted)
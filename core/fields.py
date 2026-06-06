# core/fields.py  CAMPI CRIPTATI

from django.db import models
from .encryption import encrypt_text, decrypt_text
from cryptography.fernet import InvalidToken
import logging

logger = logging.getLogger(__name__)

class EncryptedCharField(models.CharField):
    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt_text(value) if value else None

    def from_db_value(self, value, expression, connection):
        if not value: return value
        try:
            return decrypt_text(value)
        except InvalidToken:
            # ⚠️ Dato legacy non ancora criptato: restituiscilo così com'è
            logger.debug(f"🔓 Legacy data found in {self.attname}: returning raw value")
            return value

    def to_python(self, value):
        if not value or isinstance(value, str): return value
        try:
            return decrypt_text(value)
        except InvalidToken:
            return value

class EncryptedTextField(models.TextField):
    def get_prep_value(self, value):
        return encrypt_text(value) if value else None

    def from_db_value(self, value, expression, connection):
        if not value: return value
        try:
            return decrypt_text(value)
        except InvalidToken:
            logger.debug(f"🔓 Legacy data found in {self.attname}: returning raw value")
            return value

    def to_python(self, value):
        if not value or isinstance(value, str): return value
        try:
            return decrypt_text(value)
        except InvalidToken:
            return value
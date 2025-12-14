import os
import logging
from cryptography.fernet import Fernet, InvalidToken
from django.db import models
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.mail import mail_admins
logger = logging.getLogger(__name__)


def get_encryption_key():
    key = os.environ.get('FIELD_ENCRYPTION_KEY')
    if not key:
        key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    if not key:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY must be set in environment variables or Django settings"
        )
    
    if isinstance(key, str):
        key = key.encode()
    
    return Fernet(key)


class EncryptedTextField(models.TextField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fernet = None
    
    def _get_fernet(self):
        if self._fernet is None:
            self._fernet = get_encryption_key()
        return self._fernet
    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        DATA_UNAVAILABLE_PLACEHOLDER = "[DATA_UNAVAILABLE]"
        
        try:
            fernet = self._get_fernet()
            decrypted = fernet.decrypt(value.encode())
            return decrypted.decode('utf-8')
        except InvalidToken as e:
            logger.critical(
                "CRITICAL: Decryption failed for encrypted field (InvalidToken). "
                "This indicates FIELD_ENCRYPTION_KEY has been rotated or data is corrupted. "
                "IMMEDIATE ACTION REQUIRED: Check encryption key configuration."
            )
            try:
                mail_admins(
                    subject="CRITICAL: Decryption Failure Detected",
                    message=(
                        "A decryption failure has occurred in EncryptedTextField.\n\n"
                        f"Error Type: InvalidToken\n"
                        f"Error Details: {e}\n\n"
                        "WARNING: This indicates the FIELD_ENCRYPTION_KEY may be incorrect "
                        "or the encrypted data is corrupted.\n\n"
                        "IMMEDIATE ACTION REQUIRED: Verify encryption key configuration."
                    ),
                    fail_silently=True,
                )
            except Exception:
                pass  # nosec B110 - Defensive: mail_admins already has fail_silently=True
            return DATA_UNAVAILABLE_PLACEHOLDER
        except Exception as e:
            logger.critical(
                f"CRITICAL: Unexpected error decrypting field: {e}. "
                "IMMEDIATE ACTION REQUIRED: Investigate encryption subsystem."
            )
            try:
                mail_admins(
                    subject="CRITICAL: Decryption Failure Detected",
                    message=(
                        "A decryption failure has occurred in EncryptedTextField.\n\n"
                        f"Error Type: {type(e).__name__}\n"
                        f"Error Details: {e}\n\n"
                        "WARNING: This indicates the FIELD_ENCRYPTION_KEY may be incorrect "
                        "or there is an issue with the encryption subsystem.\n\n"
                        "IMMEDIATE ACTION REQUIRED: Investigate encryption configuration."
                    ),
                    fail_silently=True,
                )
            except Exception:
                pass  # nosec B110 - Defensive: mail_admins already has fail_silently=True
            return DATA_UNAVAILABLE_PLACEHOLDER
    
    def to_python(self, value):
        if isinstance(value, str) or value is None:
            return value
        return str(value)
    def get_prep_value(self, value):
        if value is None:
            return None
        if value == "[DATA_UNAVAILABLE]":
            raise ValidationError(
                "Cannot save placeholder value '[DATA_UNAVAILABLE]'. "
                "This indicates a decryption failure. Original encrypted data "
                "would be permanently lost if saved. Contact system administrator."
            )
        
        if isinstance(value, str):
            value = value.encode('utf-8')
        
        try:
            fernet = self._get_fernet()
            encrypted = fernet.encrypt(value)
            return encrypted.decode('utf-8')
        except Exception:
            logger.critical(
                "CRITICAL: Encryption failed for encrypted field. "
                "IMMEDIATE ACTION REQUIRED: Check FIELD_ENCRYPTION_KEY configuration.",
                exc_info=True
            )
            raise ValueError("Encryption failed.")


class EncryptedCharField(models.CharField):
    def __init__(self, *args, **kwargs):
        if 'max_length' not in kwargs or kwargs['max_length'] < 255:
            kwargs['max_length'] = 255
        super().__init__(*args, **kwargs)
        self._fernet = None
    
    def _get_fernet(self):
        if self._fernet is None:
            self._fernet = get_encryption_key()
        return self._fernet
    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        DATA_UNAVAILABLE_PLACEHOLDER = "[DATA_UNAVAILABLE]"
        
        try:
            fernet = self._get_fernet()
            decrypted = fernet.decrypt(value.encode())
            return decrypted.decode('utf-8')
        except InvalidToken as e:
            logger.critical(
                "CRITICAL: Decryption failed for EncryptedCharField (InvalidToken). "
                "IMMEDIATE ACTION REQUIRED: Check encryption key configuration."
            )
            try:
                mail_admins(
                    subject="CRITICAL: Decryption Failure Detected",
                    message=(
                        "A decryption failure has occurred in EncryptedCharField.\n\n"
                        f"Error Type: InvalidToken\n"
                        f"Error Details: {e}\n\n"
                        "WARNING: This indicates the FIELD_ENCRYPTION_KEY may be incorrect "
                        "or the encrypted data is corrupted.\n\n"
                        "IMMEDIATE ACTION REQUIRED: Verify encryption key configuration."
                    ),
                    fail_silently=True,
                )
            except Exception:
                pass  # nosec B110 - Defensive: mail_admins already has fail_silently=True
            return DATA_UNAVAILABLE_PLACEHOLDER
        except Exception as e:
            logger.critical(
                f"CRITICAL: Unexpected error decrypting EncryptedCharField: {e}."
            )
            try:
                mail_admins(
                    subject="CRITICAL: Decryption Failure Detected",
                    message=(
                        "A decryption failure has occurred in EncryptedCharField.\n\n"
                        f"Error Type: {type(e).__name__}\n"
                        f"Error Details: {e}\n\n"
                        "WARNING: This indicates the FIELD_ENCRYPTION_KEY may be incorrect "
                        "or there is an issue with the encryption subsystem.\n\n"
                        "IMMEDIATE ACTION REQUIRED: Investigate encryption configuration."
                    ),
                    fail_silently=True,
                )
            except Exception:
                pass  # nosec B110 - Defensive: mail_admins already has fail_silently=True
            return DATA_UNAVAILABLE_PLACEHOLDER
    
    def to_python(self, value):
        if isinstance(value, str) or value is None:
            return value
        return str(value)
    def get_prep_value(self, value):
        if value is None or value == '':
            return value
        if value == "[DATA_UNAVAILABLE]":
            raise ValidationError(
                "Cannot save placeholder value '[DATA_UNAVAILABLE]'. "
                "This indicates a decryption failure. Original encrypted data "
                "would be permanently lost if saved. Contact system administrator."
            )
        
        if isinstance(value, str):
            value = value.encode('utf-8')
        
        try:
            fernet = self._get_fernet()
            encrypted = fernet.encrypt(value)
            return encrypted.decode('utf-8')
        except Exception:
            logger.critical(
                "CRITICAL: Encryption failed for EncryptedCharField. "
                "IMMEDIATE ACTION REQUIRED: Check FIELD_ENCRYPTION_KEY configuration.",
                exc_info=True
            )
            raise ValueError("Encryption failed.")


class EncryptedDateField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 255
        kwargs.pop('auto_now', None)
        kwargs.pop('auto_now_add', None)
        super().__init__(*args, **kwargs)
        self._fernet = None
    
    def _get_fernet(self):
        if self._fernet is None:
            self._fernet = get_encryption_key()
        return self._fernet
    def from_db_value(self, value, expression, connection):
        from datetime import date
        if value is None or value == '':
            return None
        
        try:
            fernet = self._get_fernet()
            decrypted = fernet.decrypt(value.encode()).decode('utf-8')
            return date.fromisoformat(decrypted)
        except InvalidToken as e:
            logger.critical(
                "CRITICAL: Decryption failed for EncryptedDateField (InvalidToken). "
                "IMMEDIATE ACTION REQUIRED: Check encryption key configuration."
            )
            try:
                mail_admins(
                    subject="CRITICAL: Decryption Failure Detected",
                    message=(
                        "A decryption failure has occurred in EncryptedDateField.\n\n"
                        f"Error Type: InvalidToken\n"
                        f"Error Details: {e}\n\n"
                        "WARNING: This indicates the FIELD_ENCRYPTION_KEY may be incorrect "
                        "or the encrypted data is corrupted.\n\n"
                        "IMMEDIATE ACTION REQUIRED: Verify encryption key configuration."
                    ),
                    fail_silently=True,
                )
            except Exception:
                pass  # nosec B110 - Defensive: mail_admins already has fail_silently=True
            return None
        except Exception as e:
            logger.critical(
                f"CRITICAL: Unexpected error decrypting EncryptedDateField: {e}."
            )
            try:
                mail_admins(
                    subject="CRITICAL: Decryption Failure Detected",
                    message=(
                        "A decryption failure has occurred in EncryptedDateField.\n\n"
                        f"Error Type: {type(e).__name__}\n"
                        f"Error Details: {e}\n\n"
                        "WARNING: This indicates the FIELD_ENCRYPTION_KEY may be incorrect "
                        "or there is an issue with the encryption subsystem.\n\n"
                        "IMMEDIATE ACTION REQUIRED: Investigate encryption configuration."
                    ),
                    fail_silently=True,
                )
            except Exception:
                pass  # nosec B110 - Defensive: mail_admins already has fail_silently=True
            return None
    
    def to_python(self, value):
        from datetime import date
        if value is None or value == '':
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
        return None
    
    def get_prep_value(self, value):
        from datetime import date
        if value is None:
            return None
        
        if value == "[DATA_UNAVAILABLE]":
            raise ValidationError(
                "Cannot save placeholder value '[DATA_UNAVAILABLE]'. "
                "This indicates a decryption failure. Original encrypted data "
                "would be permanently lost if saved. Contact system administrator."
            )
        
        if isinstance(value, date):
            value = value.isoformat()
        
        if isinstance(value, str):
            value = value.encode('utf-8')
        
        try:
            fernet = self._get_fernet()
            encrypted = fernet.encrypt(value)
            return encrypted.decode('utf-8')
        except Exception:
            logger.critical(
                "CRITICAL: Encryption failed for EncryptedDateField. "
                "IMMEDIATE ACTION REQUIRED: Check FIELD_ENCRYPTION_KEY configuration.",
                exc_info=True
            )
            raise ValueError("Encryption failed.")

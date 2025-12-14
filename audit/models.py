from django.db import models
from django.conf import settings
from django.core.exceptions import PermissionDenied
from clinic.encrypted_fields import EncryptedCharField, EncryptedTextField


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=64)
    ip_address = EncryptedCharField(max_length=255, null=True, blank=True, help_text="Encrypted IP address")
    resource = EncryptedCharField(max_length=500, blank=True, help_text="Encrypted target resource")
    details = EncryptedTextField(blank=True, help_text="Encrypted details")
    timestamp = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-timestamp']

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionDenied("Audit records cannot be modified after creation")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Audit records cannot be deleted")

    def __str__(self):
        return f"{self.timestamp} - {self.actor} - {self.action}"


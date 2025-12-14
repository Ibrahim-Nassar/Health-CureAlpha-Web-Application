from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.conf import settings
from django.db.models.functions import Lower
import hashlib


def hash_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

class CustomUserManager(UserManager):
    @staticmethod
    def _normalize_full_email(email: str | None) -> str:
        return (email or "").strip().lower()

    def get_by_natural_key(self, username):
        try:
            return self.get(**{self.model.USERNAME_FIELD: username})
        except self.model.DoesNotExist:
            pass
        email_hash_value = hash_email(username)
        try:
            return self.get(email_hash=email_hash_value)
        except self.model.DoesNotExist:
            raise self.model.DoesNotExist()

    def create_user(self, username, email=None, password=None, **extra_fields):
        email_norm = self._normalize_full_email(email)
        if not email_norm:
            raise ValueError("Email must be set for all users.")
        extra_fields['email_hash'] = hash_email(email_norm)
        extra_fields.pop("email", None)
        return super().create_user(username, email=email_norm, password=password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        email_norm = self._normalize_full_email(email)
        if not email_norm:
            raise ValueError("Email must be set for all users.")
        extra_fields['email_hash'] = hash_email(email_norm)
        extra_fields.pop("email", None)
        return super().create_superuser(username, email=email_norm, password=password, **extra_fields)


class CustomUser(AbstractUser):
    from clinic.encrypted_fields import EncryptedCharField
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        DOCTOR = 'DOCTOR', 'Doctor'
        NURSE = 'NURSE', 'Nurse'
        PATIENT = 'PATIENT', 'Patient'

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PATIENT)
    
    email = EncryptedCharField(max_length=500, blank=False, null=False, verbose_name='email address')
    email_hash = models.CharField(max_length=64, unique=True, db_index=True, null=True, blank=True)
    
    first_name = EncryptedCharField(max_length=500, blank=True, verbose_name='first name')
    last_name = EncryptedCharField(max_length=500, blank=True, verbose_name='last name')

    objects = CustomUserManager()

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(check=~models.Q(email=""), name="customuser_email_not_blank"),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            normalized = self.email.strip().lower() if isinstance(self.email, str) else self.email
            self.email_hash = hash_email(normalized)
        return super().save(*args, **kwargs)
    
    def is_admin(self):
        return self.role == self.Role.ADMIN
    
    def is_doctor(self):
        return self.role == self.Role.DOCTOR
    
    def is_nurse(self):
        return self.role == self.Role.NURSE
    
    def is_patient(self):
        return self.role == self.Role.PATIENT

    def can_view_patient(self, patient):
        from clinic.models import Appointment
        if self.is_doctor():
            return Appointment.objects.filter(
                doctor=self,
                patient=patient,
                status__in=['CONFIRMED', 'COMPLETED']
            ).exists()
        
        if self.is_nurse():
            try:
                nurse_profile = self.nurse_profile
            except NurseProfile.DoesNotExist:
                return False
            doctor_user_ids = nurse_profile.assigned_doctors.values_list('user_id', flat=True)
            return Appointment.objects.filter(
                doctor_id__in=doctor_user_ids,
                patient=patient,
                status__in=['CONFIRMED', 'COMPLETED']
            ).exists()
        
        return False


class PatientProfile(models.Model):
    from clinic.encrypted_fields import EncryptedCharField, EncryptedTextField, EncryptedDateField
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='patient_profile')
    phone = EncryptedCharField(max_length=255, blank=True, help_text="Encrypted phone number")
    address = EncryptedTextField(blank=True, help_text="Encrypted address")
    date_of_birth = EncryptedDateField(null=True, blank=True, help_text="Encrypted date of birth")

    def __str__(self):
        return f"Patient: {self.user.username}"

class DoctorProfile(models.Model):
    from clinic.encrypted_fields import EncryptedCharField
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='doctor_profile')
    specialization = EncryptedCharField(max_length=255, blank=True, help_text="Encrypted specialization")
    
    def __str__(self):
        return f"Doctor: {self.user.username}"

class NurseProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='nurse_profile')
    assigned_doctors = models.ManyToManyField(DoctorProfile, related_name='assigned_nurses', blank=True)

    def __str__(self):
        return f"Nurse: {self.user.username}"

class TwoFactorCode(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='two_factor_codes'
    )
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_used', 'expires_at']),
        ]

    def __str__(self):
        return f"2FA Code for {self.user.username} (expires: {self.expires_at})"

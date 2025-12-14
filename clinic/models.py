from django.db import models
from django.conf import settings
from .encrypted_fields import EncryptedTextField

class Appointment(models.Model):
    class Status(models.TextChoices):
        REQUESTED = 'REQUESTED', 'Requested'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    VALID_TRANSITIONS = {
        Status.REQUESTED: [Status.CONFIRMED, Status.CANCELLED],
        Status.CONFIRMED: [Status.COMPLETED, Status.CANCELLED],
        Status.COMPLETED: [],
        Status.CANCELLED: [],
    }

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='appointments_as_patient')
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='appointments_as_doctor')
    date_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    diagnosis = EncryptedTextField(blank=True, help_text="Doctor's diagnosis after completion.")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        from datetime import timedelta
        
        if self.pk is None and self.date_time and self.date_time < timezone.now():
            raise ValidationError({'date_time': 'Appointment date cannot be in the past.'})
        
        if self.doctor and self.date_time:
            time_window_start = self.date_time - timedelta(minutes=30)
            time_window_end = self.date_time + timedelta(minutes=30)
            
            qs = Appointment.objects.filter(
                doctor=self.doctor,
                date_time__gte=time_window_start,
                date_time__lte=time_window_end,
                status__in=[self.Status.REQUESTED, self.Status.CONFIRMED]
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({
                    'date_time': 'This time slot conflicts with an existing appointment.'
                })

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.full_clean()
        super().save(*args, **kwargs)

    def can_transition_to(self, new_status):
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        return new_status in allowed

    def transition_to(self, new_status):
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        
        if not self.can_transition_to(new_status):
            raise ValidationError(
                f'Cannot transition from {self.get_status_display()} to {new_status}.'
            )
        
        now = timezone.now()
        if new_status == self.Status.CONFIRMED:
            if self.date_time and self.date_time <= now:
                raise ValidationError("Cannot confirm an appointment scheduled in the past.")
        
        if new_status == self.Status.COMPLETED:
            if self.date_time and self.date_time > now:
                raise ValidationError("Cannot complete an appointment before its scheduled time.")
        
        self.status = new_status
        self.save()

    def __str__(self):
        return f"Appt: {self.patient} with {self.doctor} on {self.date_time}"


class MedicalNote(models.Model):
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='medical_notes')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='authored_notes')
    content = EncryptedTextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return f"Note for {self.patient} by {self.author}"

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser, DoctorProfile, NurseProfile, PatientProfile
from .models import Appointment, MedicalNote


class ProfileForm(forms.ModelForm):
    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter your phone number',
            'class': 'w-full p-2 rounded bg-gray-800 border border-gray-600 focus:border-primary focus:outline-none'
        })
    )
    address = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Enter your address',
            'class': 'w-full p-2 rounded bg-gray-800 border border-gray-600 focus:border-primary focus:outline-none'
        })
    )
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full p-2 rounded bg-gray-800 border border-gray-600 focus:border-primary focus:outline-none'
        })
    )
    class Meta:
        model = PatientProfile
        fields = ['phone', 'address', 'date_of_birth']
    
    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob and dob > timezone.now().date():
            raise ValidationError('Date of birth cannot be in the future.')
        return dob

class NurseAssignmentForm(forms.ModelForm):
    assigned_doctors = forms.ModelMultipleChoiceField(
        queryset=DoctorProfile.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select the doctors this nurse should be assigned to."
    )
    class Meta:
        model = NurseProfile
        fields = ['assigned_doctors']


class AppointmentForm(forms.ModelForm):
    doctor = forms.ModelChoiceField(
        queryset=CustomUser.objects.filter(role=CustomUser.Role.DOCTOR, is_active=True),
        label="Select Doctor"
    )
    date_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        label="Requested Date/Time"
    )

    class Meta:
        model = Appointment
        fields = ['doctor', 'date_time']
    
    def clean_date_time(self):
        date_time = self.cleaned_data.get('date_time')
        if date_time and date_time <= timezone.now():
            raise ValidationError('Appointment must be scheduled in the future.')
        return date_time
    def clean(self):
        cleaned_data = super().clean()
        doctor = cleaned_data.get('doctor')
        date_time = cleaned_data.get('date_time')
        if doctor and date_time:
            from datetime import timedelta
            time_window_start = date_time - timedelta(minutes=30)
            time_window_end = date_time + timedelta(minutes=30)
            
            exists = Appointment.objects.filter(
                doctor=doctor,
                date_time__gte=time_window_start,
                date_time__lte=time_window_end,
                status__in=[Appointment.Status.REQUESTED, Appointment.Status.CONFIRMED]
            ).exists()
            
            if exists:
                raise ValidationError(
                    'This time slot conflicts with an existing appointment. '
                    'Please choose a different time.'
                )
        
        return cleaned_data

class DiagnosisForm(forms.ModelForm):
    diagnosis = forms.CharField(
        required=False,
        max_length=5000,
        widget=forms.Textarea(attrs={'rows': 4}),
    )

    class Meta:
        model = Appointment
        fields = ['diagnosis']
        widgets = {
            'diagnosis': forms.Textarea(attrs={'rows': 4}),
        }

class MedicalNoteForm(forms.ModelForm):
    content = forms.CharField(
        max_length=5000,
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    class Meta:
        model = MedicalNote
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3}),
        }

class StaffCreationForm(UserCreationForm):
    role = forms.ChoiceField(choices=[
        (CustomUser.Role.DOCTOR, 'Doctor'),
        (CustomUser.Role.NURSE, 'Nurse')
    ])
    email = forms.EmailField(
        required=True,
        help_text='Required. Staff must have a unique email for 2FA.'
    )
    specialization = forms.CharField(max_length=100, required=False, help_text="For Doctors")
    assigned_doctors = forms.ModelMultipleChoiceField(
        queryset=DoctorProfile.objects.all(),
        required=False,
        help_text="For Nurses: Assign to doctors"
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = UserCreationForm.Meta.fields + ('email', 'role',)
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower().strip()
            from accounts.models import hash_email
            email_hash_value = hash_email(email)
            if CustomUser.objects.filter(email_hash=email_hash_value).exists():
                raise ValidationError('A user with this email address already exists.')
        return email
    def save(self, commit=True):
        user = super().save(commit=False)
        role = self.cleaned_data['role']
        user.role = role
        user.email = self.cleaned_data['email'].lower().strip()
        if commit:
            with transaction.atomic():
                user.save()
                if role == CustomUser.Role.DOCTOR:
                    DoctorProfile.objects.create(
                        user=user,
                        specialization=self.cleaned_data.get('specialization', '')
                    )
                elif role == CustomUser.Role.NURSE:
                    nurse_profile = NurseProfile.objects.create(user=user)
                    nurse_profile.assigned_doctors.set(self.cleaned_data.get('assigned_doctors', []))
        return user


class PatientCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        help_text='Required. Patient must have a unique email for 2FA and notifications.'
    )
    first_name = forms.CharField(
        max_length=150,
        required=False,
        help_text='Optional. Patient first name.'
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        help_text='Optional. Patient last name.'
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        help_text='Patient phone number.'
    )
    address = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        help_text='Patient address.'
    )
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='Patient date of birth.'
    )
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name',)
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower().strip()
            from accounts.models import hash_email
            email_hash_value = hash_email(email)
            if CustomUser.objects.filter(email_hash=email_hash_value).exists():
                raise ValidationError('A user with this email address already exists.')
        return email
    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob and dob > timezone.now().date():
            raise ValidationError('Date of birth cannot be in the future.')
        return dob
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = CustomUser.Role.PATIENT
        user.email = self.cleaned_data['email'].lower().strip()
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        if commit:
            with transaction.atomic():
                user.save()
                PatientProfile.objects.create(
                    user=user,
                    phone=self.cleaned_data.get('phone', ''),
                    address=self.cleaned_data.get('address', ''),
                    date_of_birth=self.cleaned_data.get('date_of_birth')
                )
        return user

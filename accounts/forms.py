from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate
from django.db import transaction

from .models import CustomUser, PatientProfile, hash_email

class PatientRegistrationForm(UserCreationForm):
    phone = forms.CharField(max_length=20, required=True)
    address = forms.CharField(max_length=500, widget=forms.Textarea, required=True)
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=True
    )
    email = forms.EmailField(
        required=True,
        help_text='Required. A verification code will be sent to this email for login.'
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = UserCreationForm.Meta.fields + ('email',)

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower().strip()
            email_hash_value = hash_email(email)
            if CustomUser.objects.filter(email_hash=email_hash_value).exists():
                raise ValidationError('A user with this email address already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email'].lower().strip()  
        user.role = CustomUser.Role.PATIENT
        if commit:
            with transaction.atomic():
                user.save()
                PatientProfile.objects.create(
                    user=user,
                    phone=self.cleaned_data['phone'],
                    address=self.cleaned_data['address'],
                    date_of_birth=self.cleaned_data['date_of_birth']
                )
        return user

class TwoFactorLoginForm(AuthenticationForm):
    pass
class TwoFactorVerifyForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': '000000',
            'pattern': '[0-9]{6}',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'class': 'w-full p-2 rounded bg-gray-800 border border-gray-600 focus:border-primary focus:outline-none text-center text-2xl tracking-widest'
        }),
        help_text='Enter the 6-digit code sent to your email.'
    )
    def clean_code(self):
        code = self.cleaned_data.get('code')
        if code:
            if not code.isdigit():
                raise ValidationError('Code must contain only digits.')
            if len(code) != 6:
                raise ValidationError('Code must be exactly 6 digits.')
        return code


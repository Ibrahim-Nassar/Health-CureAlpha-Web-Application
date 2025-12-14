import secrets
import logging
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.conf import settings
from .models import TwoFactorCode
logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
EXPIRY_MINUTES = 10


def generate_otp_code() -> str:
    code = secrets.randbelow(10**6)
    return f"{code:06d}"

def hash_otp_code(raw_code: str) -> str:
    return make_password(raw_code)

def create_2fa_code_for_user(user):
    TwoFactorCode.objects.filter(
        user=user,
        is_used=False,
        expires_at__gt=timezone.now()
    ).update(is_used=True)
    raw_code = generate_otp_code()
    code_hash = hash_otp_code(raw_code)
    
    expires_at = timezone.now() + timedelta(minutes=EXPIRY_MINUTES)
    TwoFactorCode.objects.create(
        user=user,
        code_hash=code_hash,
        expires_at=expires_at,
        attempts=0,
        is_used=False
    )
    
    return raw_code


def verify_2fa_code(user, submitted_code: str):
    from django.db import transaction
    now = timezone.now()
    
    with transaction.atomic():
        code_obj = TwoFactorCode.objects.select_for_update().filter(
            user=user,
            is_used=False,
            expires_at__gt=now
        ).order_by('-created_at').first()
        
        if not code_obj:
            return (False, "expired_or_missing")
        
        if code_obj.attempts >= MAX_ATTEMPTS:
            code_obj.is_used = True
            code_obj.save()
            return (False, "too_many_attempts")
        
        code_obj.attempts += 1
        code_obj.save()
        
        if check_password(submitted_code, code_obj.code_hash):
            code_obj.is_used = True
            code_obj.save()
            return (True, None)
        else:
            return (False, "invalid_code")


def send_2fa_email(user, otp_code):
    try:
        subject = "Your login verification code"
        message = f"Your verification code is: {otp_code}\n\nThis code will expire in {EXPIRY_MINUTES} minutes."
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [user.email]
        
        send_mail(subject, message, from_email, recipient_list, fail_silently=False)
        logger.info(f"2FA email sent to user {user.username}")
        return True
    except Exception as e:
        logger.error(f"Failed to send 2FA email to user {user.username}: {str(e)}")
        return False

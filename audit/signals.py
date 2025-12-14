from django.contrib.auth.signals import user_logged_in, user_login_failed, user_logged_out
from django.dispatch import receiver, Signal
from django.core.cache import cache
from .utils import log_action, get_client_ip, make_rate_limit_key, increment_rate_limit, normalize_rate_limit_username, sanitize_username_for_logging

LOCKOUT_THRESHOLD = 5
LOCKOUT_TIME = 900

twofa_verification_failed = Signal()


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    ip = get_client_ip(request)
    if ip:
        username = user.username if user else None
        cache.delete(make_rate_limit_key('login_failures', ip))
        cache.delete(make_rate_limit_key('2fa_failures', ip))
        if username:
            cache.delete(make_rate_limit_key('login_failures', ip, username=username))
            cache.delete(make_rate_limit_key('2fa_failures', ip, username=username))
    log_action(request, "LOGIN_SUCCESS", f"User: {user.username}", user_obj=user)


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    username = credentials.get('username', 'unknown')
    safe_username = sanitize_username_for_logging(username)
    
    increment_rate_limit(request, 'login_failures')
    
    log_action(request, "LOGIN_FAILED", f"Attempted Username: {safe_username}")


@receiver(twofa_verification_failed)
def log_2fa_verification_failed(sender, request, user, **kwargs):
    increment_rate_limit(request, '2fa_failures')
    log_action(
        request,
        "2FA_VERIFY_FAILED",
        f"User: {user.username if user else 'unknown'}",
        user_obj=user
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    if user:
        log_action(request, "LOGOUT", f"User: {user.username}", user_obj=user)
    else:
        log_action(request, "LOGOUT", "User: unknown")
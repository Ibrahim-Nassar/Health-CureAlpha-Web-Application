from django.conf import settings
from .models import AuditLog
import re


_INVALID_CACHE_KEY_CHARS_RE = re.compile(r"[\x00-\x20\x7f]+")
_RATE_LIMIT_USERNAME_MAX_LEN = 150  


def get_client_ip(request):
    if not request:
        return None
    
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
        if ip:
            return ip
    
    return request.META.get('REMOTE_ADDR')


def normalize_rate_limit_username(username):
    if not username:
        return None
    try:
        username = str(username)
    except Exception:
        return None

    username = username.strip().lower()
    if not username:
        return None

    username = _INVALID_CACHE_KEY_CHARS_RE.sub("", username)
    if not username:
        return None

    if len(username) > _RATE_LIMIT_USERNAME_MAX_LEN:
        username = username[:_RATE_LIMIT_USERNAME_MAX_LEN]

    return username


def make_rate_limit_key(prefix, ip, username=None):
    ip_part = (ip or "unknown")
    ip_part = _INVALID_CACHE_KEY_CHARS_RE.sub("", str(ip_part).strip()) or "unknown"
    username_part = normalize_rate_limit_username(username)
    if username_part:
        return f"{prefix}_{ip_part}_{username_part}"
    return f"{prefix}_{ip_part}"

def log_action(request, action, resource="", details="", user_obj=None):
    ip = get_client_ip(request)
    actor = user_obj
    if not actor and request and hasattr(request, 'user') and request.user.is_authenticated:
        actor = request.user
    
    AuditLog.objects.create(
        actor=actor,
        action=action,
        ip_address=ip,
        resource=resource,
        details=details
    )


RATE_LIMIT_TIMEOUT = 900


def increment_rate_limit(request, prefix):
    from django.core.cache import cache
    ip = get_client_ip(request)
    if not ip:
        return 0
    
    username = None
    if request.method == 'POST':
        username = normalize_rate_limit_username(request.POST.get('username', ''))
    
    if not username and hasattr(request, 'user') and request.user.is_authenticated:
        username = normalize_rate_limit_username(getattr(request.user, 'username', None))
    
    if not username and prefix == '2fa_failures':
        try:
            pending_user_id = request.session.get('pending_2fa_user_id')
            if pending_user_id:
                from accounts.models import CustomUser
                user = CustomUser.objects.only('username').get(id=pending_user_id)
                username = normalize_rate_limit_username(user.username)
        except Exception:
            pass  # nosec B110 - Intentional: rate limiting proceeds without username if lookup fails
    
    key = make_rate_limit_key(prefix, ip, username=username)
    failures = cache.get(key, 0)
    new_count = failures + 1
    cache.set(key, new_count, RATE_LIMIT_TIMEOUT)
    
    return new_count


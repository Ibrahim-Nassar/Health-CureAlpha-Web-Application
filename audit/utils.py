from django.conf import settings
from .models import AuditLog
import re
from django.http import HttpResponse
from django.shortcuts import render


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


def _extract_patient_identifiers(patients, limit=10):
    """
    Safely capture a limited set of patient identifiers (usernames) without
    forcing evaluation of large querysets.
    """
    if patients is None:
        return [], False

    usernames = []
    truncated = False

    try:
        iterable = patients[: limit + 1]
    except Exception:
        iterable = patients

    count = 0
    for entry in iterable:
        count += 1
        username = None
        if hasattr(entry, "user"):
            username = getattr(entry.user, "username", None)
        if username is None:
            username = getattr(entry, "username", None)
        if username:
            username = str(username).strip()
            if username and username not in usernames:
                usernames.append(username)
        if count > limit:
            truncated = True
            break
    return usernames[:limit], truncated


def log_phi_view(request, action, resource="PHI_READ", patients=None, patient_usernames=None, extra_details=""):
    """
    Log read access to patient health information (PHI) using the existing
    audit log model. Captures the actor, IP (via log_action), and which patient
    records were viewed (limited to avoid excess logging).
    """
    usernames = []

    if patient_usernames:
        for raw in patient_usernames:
            if not raw:
                continue
            normalized = str(raw).strip()
            if normalized and normalized not in usernames:
                usernames.append(normalized)

    extracted, truncated = _extract_patient_identifiers(patients, limit=10)
    for uname in extracted:
        if uname not in usernames:
            usernames.append(uname)

    details_parts = []
    if usernames:
        details_parts.append(f"Patients: {', '.join(usernames)}")
        if truncated:
            details_parts.append("patient_list_truncated=True")
    if extra_details:
        details_parts.append(extra_details)

    log_action(
        request,
        action=action,
        resource=resource or "PHI_READ",
        details=" | ".join(details_parts),
    )


def sanitize_username_for_logging(username):
    """
    Avoid leaking possible passwords or long identifiers in audit logs.
    Mirrors previous logic from signals to prevent circular imports.
    """
    if not username:
        return '[empty]'
    username = str(username)
    has_special = any(c in username for c in '!@#$%^&*()_+-=[]{}|;:,.<>?')
    is_long = len(username) > 30
    has_mixed_case = any(c.isupper() for c in username) and any(c.islower() for c in username)
    has_numbers = any(c.isdigit() for c in username)
    password_indicators = sum([has_special, is_long, has_mixed_case and has_numbers])
    if password_indicators >= 2:
        return '[REDACTED - possible password]'
    if len(username) > 50:
        return username[:20] + '...[truncated]'
    return username


RATE_LIMIT_TIMEOUT = 900
RATE_LIMIT_MAX_TIMEOUT = 3600
_PROGRESSIVE_PREFIXES = {"login_failures", "2fa_failures"}
_RATE_LIMIT_THRESHOLDS = {
    "login_failures": 5,
    "2fa_failures": 5,
}


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


def _progressive_timeout(prefix, new_count, limit, base_timeout):
    if prefix not in _PROGRESSIVE_PREFIXES:
        return base_timeout
    if new_count <= limit:
        return base_timeout
    # Linear growth after threshold, bounded
    over = new_count - limit + 1
    multiplier = min(max(1, over), 4)  # cap to avoid long lockouts
    return min(base_timeout * multiplier, RATE_LIMIT_MAX_TIMEOUT)


def rate_limit_blocked_response(request, prefix, limit, *, identifier=None, template='429.html', base_timeout=RATE_LIMIT_TIMEOUT):
    """
    Increment rate-limit bucket (ip + optional identifier). Apply progressive TTL
    for login/2fa prefixes. If over limit, log once and return a 429 response.
    """
    from django.core.cache import cache

    ip = get_client_ip(request)
    normalized_identifier = normalize_rate_limit_username(identifier)
    key = make_rate_limit_key(prefix, ip, username=normalized_identifier)

    current = cache.get(key, 0)
    new_count = current + 1
    ttl = _progressive_timeout(prefix, new_count, limit, base_timeout)
    cache.set(key, new_count, ttl)

    if new_count > limit:
        safe_identifier = sanitize_username_for_logging(identifier or "")
        details = f"identifier={safe_identifier}, ip={ip}"
        log_action(request, "RATE_LIMIT_BLOCK", resource=prefix, details=details)
        try:
            return render(request, template, status=429)
        except Exception:
            return HttpResponse("Too Many Requests", status=429)

    return None


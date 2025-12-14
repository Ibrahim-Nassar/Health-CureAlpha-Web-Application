from django.core.cache import cache
from django.shortcuts import render
from django.urls import reverse
from .utils import get_client_ip, make_rate_limit_key, normalize_rate_limit_username

class AuditMiddleware:
    LOGIN_RATE_LIMIT = 5
    VERIFY_2FA_RATE_LIMIT = 5
    REGISTER_RATE_LIMIT = 10
    REGISTER_RATE_LIMIT_TIMEOUT = 3600
    
    def __init__(self, get_response):
        self.get_response = get_response

    def _get_rate_limit_key(self, request, prefix):
        ip = get_client_ip(request)
        username = None
        if request.method == 'POST':
            username = normalize_rate_limit_username(request.POST.get('username', ''))
        
        if not username and hasattr(request, 'user') and request.user.is_authenticated:
            username = normalize_rate_limit_username(getattr(request.user, 'username', None))
        
        if not username and prefix == '2fa_failures':
            try:
                pending_user_id = request.session.get('pending_2fa_user_id')
            except Exception:
                pending_user_id = None
            if pending_user_id:
                try:
                    from accounts.models import CustomUser
                    username = normalize_rate_limit_username((
                        CustomUser.objects.only('username')
                        .get(id=pending_user_id)
                        .username.lower()
                    ))
                except Exception:
                    username = None

        return make_rate_limit_key(prefix, ip, username=username)

    def __call__(self, request):
        if request.path == reverse('login') and request.method == 'POST':
            key = self._get_rate_limit_key(request, 'login_failures')
            failures = cache.get(key, 0)
            if failures >= self.LOGIN_RATE_LIMIT:
                return render(request, '429.html', status=429)
        
        if request.path == reverse('verify_2fa') and request.method == 'POST':
            key = self._get_rate_limit_key(request, '2fa_failures')
            failures = cache.get(key, 0)
            if failures >= self.VERIFY_2FA_RATE_LIMIT:
                return render(request, '429.html', status=429)
        
        if request.path.startswith('/accounts/register/'):
            import hashlib
            
            ip = get_client_ip(request)
            
            session_key = getattr(request.session, 'session_key', '') or ''
            
            if session_key:
                composite_suffix = hashlib.md5(session_key.encode(), usedforsecurity=False).hexdigest()[:16]
            else:
                composite_suffix = "nosession"
            
            key = f"register_dos_{ip}_{composite_suffix}"
            
            limit = 3 
            count = cache.get(key, 0)
            
            if count >= limit:
                try:
                    return render(request, '429.html', status=429)
                except Exception:
                    from django.http import HttpResponse
                    return HttpResponse("Too Many Requests", status=429)
            
            cache.set(key, count + 1, timeout=300)

        response = self.get_response(request)
        
        response['X-Frame-Options'] = 'DENY'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        response['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "font-src 'self'; "
            "img-src 'self' data:; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self';"
        )

        return response



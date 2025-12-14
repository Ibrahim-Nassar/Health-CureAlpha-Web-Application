from django.shortcuts import render, redirect
from django.views.generic import TemplateView, CreateView, View, FormView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.utils import timezone
from django.utils.timezone import is_naive, make_aware, get_current_timezone
from django.utils.dateparse import parse_datetime
from django.contrib import messages
from django.conf import settings
from django.core.cache import cache


from .forms import PatientRegistrationForm, TwoFactorLoginForm, TwoFactorVerifyForm
from .utils import create_2fa_code_for_user, send_2fa_email, verify_2fa_code
from audit.utils import log_action, get_client_ip, make_rate_limit_key, increment_rate_limit
from audit.signals import twofa_verification_failed

TWO_FA_SESSION_TIMEOUT_SECONDS = 900

class HomeView(TemplateView):
    template_name = 'home.html'

class PatientRegisterView(CreateView):
    form_class = PatientRegistrationForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request, "REGISTER_PATIENT", f"User: {self.object.username}")
        messages.success(
            self.request, 
            'Account created successfully. Please log in with your credentials.'
        )
        return response

class TwoFactorLoginView(FormView):
    template_name = 'accounts/login.html'
    form_class = TwoFactorLoginForm
    success_url = reverse_lazy('verify_2fa')
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs
    def form_valid(self, form):
        user = form.get_user()
        if user is None:
            form.add_error(None, 'Authentication failed. Please try again.')
            return self.form_invalid(form)
        
        if not user.is_active:
            form.add_error(None, 'This account is inactive.')
            return self.form_invalid(form)
        
        
        try:
            otp_code = create_2fa_code_for_user(user)
            email_sent = send_2fa_email(user, otp_code)
            
            if not email_sent:
                form.add_error(None, 'Failed to send verification email. Please try again later.')
                return self.form_invalid(form)
            
            self.request.session['pending_2fa_user_id'] = user.id
            self.request.session['pending_2fa_created_at'] = timezone.now().isoformat()
            
            log_action(self.request, "2FA_CODE_SENT", f"User: {user.username}")
            
            return super().form_valid(form)
        except Exception as e:
            form.add_error(None, 'An error occurred. Please try again.')
            log_action(
                self.request,
                "2FA_ERROR",
                resource=f"User: {user.username}",
                details=f"Exception: {type(e).__name__}",
            )
            return self.form_invalid(form)

    def form_invalid(self, form):
        increment_rate_limit(self.request, 'login_failures')
        return super().form_invalid(form)
    def get_success_url(self):
        return reverse_lazy('verify_2fa')


class TwoFactorVerifyView(FormView):
    template_name = 'accounts/verify_2fa.html'
    form_class = TwoFactorVerifyForm
    success_url = reverse_lazy('dashboard')
    def dispatch(self, request, *args, **kwargs):
        if 'pending_2fa_user_id' not in request.session:
            messages.error(request, 'Please log in first.')
            return redirect('login')
        
        created_at_str = request.session.get('pending_2fa_created_at')
        if created_at_str:
            created_at = parse_datetime(created_at_str)
            if created_at:
                try:
                    if is_naive(created_at):
                        created_at = make_aware(created_at, get_current_timezone())
                    elapsed = (timezone.now() - created_at).total_seconds()
                except Exception:
                    self._clear_pending_session()
                    messages.error(request, 'Session expired. Please log in again.')
                    return redirect('login')
                if elapsed > TWO_FA_SESSION_TIMEOUT_SECONDS:
                    self._clear_pending_session()
                    messages.error(request, 'Session expired. Please log in again.')
                    return redirect('login')
        
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_id = self.request.session.get('pending_2fa_user_id')
        if user_id:
            try:
                from .models import CustomUser
                user = CustomUser.objects.get(id=user_id)
                email = user.email
                if '@' in email:
                    local, domain = email.split('@', 1)
                    masked_email = f"{local[0]}***@{domain}" if len(local) > 1 else f"*@{domain}"
                    context['masked_email'] = masked_email
            except CustomUser.DoesNotExist:
                pass
        return context

    def form_valid(self, form):
        user_id = self.request.session.get('pending_2fa_user_id')
        submitted_code = form.cleaned_data.get('code')
        
        if not user_id:
            messages.error(self.request, 'Session expired. Please log in again.')
            return redirect('login')
        
        try:
            from .models import CustomUser
            user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            messages.error(self.request, 'Invalid session. Please log in again.')
            self._clear_pending_session()
            return redirect('login')

        if not user.is_active:
            messages.error(self.request, 'This account is inactive.')
            log_action(self.request, "LOGIN_INACTIVE", f"User: {user.username}", user_obj=user)
            self._clear_pending_session()
            return redirect('login')
        
        success, error_reason = verify_2fa_code(user, submitted_code)
        
        if success:
            login(self.request, user)
            
            self._clear_pending_session()
            
            
            messages.success(self.request, 'Login successful!')
            return redirect(self.get_success_url())
        else:
            twofa_verification_failed.send(
                sender=self.__class__,
                request=self.request,
                user=user
            )
            
            if error_reason == "too_many_attempts":
                messages.error(self.request, 'Too many failed attempts. Please log in again.')
                self._clear_pending_session()
                return redirect('login')
            elif error_reason == "expired_or_missing":
                messages.error(self.request, 'Code expired or invalid. Please log in again.')
                self._clear_pending_session()
                return redirect('login')
            else:
                increment_rate_limit(self.request, '2fa_failures')
                form.add_error('code', 'Invalid or expired code. Please try again.')
                return self.form_invalid(form)

    def _clear_pending_session(self):
        if 'pending_2fa_user_id' in self.request.session:
            del self.request.session['pending_2fa_user_id']
        if 'pending_2fa_created_at' in self.request.session:
            del self.request.session['pending_2fa_created_at']
    def get_success_url(self):
        return reverse_lazy('dashboard')


class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        if user.is_admin():
            return redirect('clinic:admin_dashboard')
        elif user.is_doctor():
            return redirect('clinic:doctor_dashboard')
        elif user.is_nurse():
            return redirect('clinic:nurse_dashboard')
        elif user.is_patient():
            return redirect('clinic:patient_dashboard')
        return redirect('home')


class LoggedPasswordChangeView(auth_views.PasswordChangeView):
    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request, "PASSWORD_CHANGE", f"User: {self.request.user.username}")
        return response


class LoggedPasswordResetView(auth_views.PasswordResetView):
    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request, "PASSWORD_RESET_REQUEST", "Password reset requested")
        return response


class LoggedPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    def form_valid(self, form):
        response = super().form_valid(form)
        user = getattr(self, "user", None)
        if user:
            log_action(self.request, "PASSWORD_RESET_COMPLETE", f"User: {user.username}", user_obj=user)
        else:
            log_action(self.request, "PASSWORD_RESET_COMPLETE", "User: unknown")
        return response


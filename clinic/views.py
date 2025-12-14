from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, View, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.db.models import Q, Prefetch
from django.core.exceptions import PermissionDenied

from accounts.models import CustomUser, DoctorProfile, NurseProfile, PatientProfile
from .models import Appointment, MedicalNote
from .forms import AppointmentForm, DiagnosisForm, MedicalNoteForm, StaffCreationForm, ProfileForm, NurseAssignmentForm, PatientCreationForm
from audit.utils import log_action
from audit.models import AuditLog


class RoleRequiredMixin(UserPassesTestMixin):
    allowed_roles = []
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.role in self.allowed_roles

class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = [CustomUser.Role.ADMIN]

class DoctorRequiredMixin(RoleRequiredMixin):
    allowed_roles = [CustomUser.Role.DOCTOR]

class NurseRequiredMixin(RoleRequiredMixin):
    allowed_roles = [CustomUser.Role.NURSE]

class PatientRequiredMixin(RoleRequiredMixin):
    allowed_roles = [CustomUser.Role.PATIENT]


class AdminDashboardView(AdminRequiredMixin, TemplateView):
    template_name = 'clinic/admin_dashboard.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['doctor_count'] = CustomUser.objects.filter(role=CustomUser.Role.DOCTOR).count()
        ctx['nurse_count'] = CustomUser.objects.filter(role=CustomUser.Role.NURSE).count()
        ctx['patient_count'] = CustomUser.objects.filter(role=CustomUser.Role.PATIENT).count()
        ctx['appt_count'] = Appointment.objects.count()
        ctx['recent_appointments'] = Appointment.objects.select_related(
            'patient', 'doctor'
        ).order_by('-created_at')[:10]
        return ctx


class AdminPatientListView(AdminRequiredMixin, ListView):
    model = PatientProfile
    template_name = 'clinic/admin_patient_list.html'
    context_object_name = 'patients'
    paginate_by = 20
    def get_queryset(self):
        return PatientProfile.objects.select_related('user').order_by('user__username')


class AdminAppointmentListView(AdminRequiredMixin, ListView):
    model = Appointment
    template_name = 'clinic/admin_appointment_list.html'
    context_object_name = 'appointments'
    paginate_by = 30
    def get_queryset(self):
        qs = Appointment.objects.select_related('patient', 'doctor').order_by('-date_time')
        status = self.request.GET.get('status')
        doctor_id = self.request.GET.get('doctor')
        if status:
            qs = qs.filter(status=status)
        if doctor_id:
            doctor_id = doctor_id.strip()
            if doctor_id.isdigit():
                qs = qs.filter(doctor_id=int(doctor_id))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['doctors'] = CustomUser.objects.filter(role=CustomUser.Role.DOCTOR)
        ctx['statuses'] = Appointment.Status.choices
        return ctx

class DoctorDashboardView(DoctorRequiredMixin, ListView):
    model = Appointment
    template_name = 'clinic/doctor_dashboard.html'
    context_object_name = 'appointments'

    def get_queryset(self):
        show_all = self.request.GET.get('show_all') == '1'
        qs = Appointment.objects.filter(doctor=self.request.user)
        if not show_all:
            qs = qs.exclude(status=Appointment.Status.CANCELLED)
        return qs.order_by('date_time')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        patient_ids = Appointment.objects.filter(doctor=self.request.user).values_list('patient_id', flat=True)
        ctx['my_patients'] = PatientProfile.objects.filter(user_id__in=patient_ids)
        ctx['show_all'] = self.request.GET.get('show_all') == '1'
        ctx['now'] = timezone.now()
        return ctx


class DoctorAppointmentHistoryView(DoctorRequiredMixin, ListView):
    model = Appointment
    template_name = 'clinic/doctor_appointment_history.html'
    context_object_name = 'appointments'
    paginate_by = 20
    def get_queryset(self):
        qs = Appointment.objects.filter(doctor=self.request.user)
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-date_time')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = Appointment.Status.choices
        return ctx

class NurseDashboardView(NurseRequiredMixin, TemplateView):
    template_name = 'clinic/nurse_dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        try:
            nurse_profile = self.request.user.nurse_profile
        except NurseProfile.DoesNotExist:
            ctx['assigned_doctors'] = []
            ctx['patients'] = PatientProfile.objects.none()
            ctx['upcoming_appointments'] = Appointment.objects.none()
            messages.warning(self.request, "Your profile is incomplete. Please contact admin.")
            return ctx
        
        doctors = nurse_profile.assigned_doctors.all()
        doctor_users = [d.user for d in doctors]
        patient_ids = Appointment.objects.filter(doctor__in=doctor_users).values_list('patient_id', flat=True).distinct()
        
        patients = PatientProfile.objects.filter(user_id__in=patient_ids).select_related('user')
        
        patient_doctors = {}
        for appt in Appointment.objects.filter(doctor__in=doctor_users).select_related('doctor'):
            if appt.patient_id not in patient_doctors:
                patient_doctors[appt.patient_id] = set()
            patient_doctors[appt.patient_id].add(appt.doctor.username)
        
        for patient in patients:
            patient.doctor_names = ', '.join(patient_doctors.get(patient.user_id, []))
        
        ctx['assigned_doctors'] = doctors
        ctx['patients'] = patients
        
        ctx['upcoming_appointments'] = Appointment.objects.filter(
            doctor__in=doctor_users,
            status__in=[Appointment.Status.REQUESTED, Appointment.Status.CONFIRMED],
            date_time__gte=timezone.now()
        ).select_related('patient', 'doctor').order_by('date_time')[:10]
        
        return ctx

class PatientDashboardView(PatientRequiredMixin, ListView):
    model = Appointment
    template_name = 'clinic/patient_dashboard.html'
    context_object_name = 'appointments'

    def get_queryset(self):
        return Appointment.objects.filter(patient=self.request.user).order_by('-date_time')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['my_notes'] = MedicalNote.objects.filter(patient=self.request.user).order_by('-created_at')
        ctx['now'] = timezone.now()
        return ctx


class ProfileEditView(PatientRequiredMixin, UpdateView):
    model = PatientProfile
    form_class = ProfileForm
    template_name = 'clinic/edit_profile.html'
    success_url = reverse_lazy('clinic:patient_dashboard')
    def get_object(self, queryset=None):
        profile, created = PatientProfile.objects.get_or_create(user=self.request.user)
        return profile
    def form_valid(self, form):
        messages.success(self.request, 'Your profile has been updated successfully.')
        log_action(self.request, "EDIT_PROFILE", f"User: {self.request.user.username}")
        return super().form_valid(form)


class BookAppointmentView(PatientRequiredMixin, CreateView):
    model = Appointment
    form_class = AppointmentForm
    template_name = 'clinic/book_appointment.html'
    success_url = reverse_lazy('clinic:patient_dashboard')

    def form_valid(self, form):
        form.instance.patient = self.request.user
        form.instance.status = Appointment.Status.REQUESTED
        log_action(self.request, "REQUEST_APPOINTMENT", f"Doctor: {form.instance.doctor.username}")
        return super().form_valid(form)


class PatientCancelAppointmentView(PatientRequiredMixin, View):
    def post(self, request, pk):
        appt = get_object_or_404(Appointment, pk=pk, patient=request.user)

        if appt.date_time and appt.date_time <= timezone.now():
            messages.error(request, "You cannot cancel an appointment after its scheduled time.")
            return redirect('clinic:patient_dashboard')

        if appt.status not in [Appointment.Status.REQUESTED, Appointment.Status.CONFIRMED]:
            messages.error(request, "This appointment cannot be cancelled.")
            return redirect('clinic:patient_dashboard')

        previous_status = appt.status
        appt.status = Appointment.Status.CANCELLED
        appt.save(update_fields=["status", "updated_at"])
        log_action(
            request,
            "PATIENT_CANCEL_APPT",
            f"Appt ID: {pk}",
            f"Previous Status: {previous_status} -> New Status: {Appointment.Status.CANCELLED}",
        )
        messages.success(request, "Appointment cancelled successfully.")
        return redirect('clinic:patient_dashboard')

class UpdateAppointmentStatusView(DoctorRequiredMixin, View):
    def post(self, request, pk):
        from django.core.exceptions import ValidationError
        appt = get_object_or_404(Appointment, pk=pk, doctor=request.user)
        action = request.POST.get('action')
        
        status_map = {
            'confirm': Appointment.Status.CONFIRMED,
            'cancel': Appointment.Status.CANCELLED,
            'complete': Appointment.Status.COMPLETED,
        }
        new_status = status_map.get(action)
        if not new_status:
            messages.error(request, 'Invalid action.')
            return redirect('clinic:doctor_dashboard')
        
        try:
            appt.transition_to(new_status)
            log_action(request, "UPDATE_APPT_STATUS", f"Appt ID: {pk}, Status: {appt.status}")
            messages.success(request, f'Appointment status updated to {appt.get_status_display()}.')
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, 'message') else str(e.messages[0] if e.messages else e))
        
        return redirect('clinic:doctor_dashboard')

class AddDiagnosisView(DoctorRequiredMixin, UpdateView):
    model = Appointment
    form_class = DiagnosisForm
    template_name = 'clinic/add_diagnosis.html'
    success_url = reverse_lazy('clinic:doctor_dashboard')

    def get_queryset(self):
        return Appointment.objects.filter(doctor=self.request.user, status=Appointment.Status.COMPLETED)

    def form_valid(self, form):
        log_action(self.request, "ADD_DIAGNOSIS", f"Appt ID: {self.object.id}")
        return super().form_valid(form)

    def _get_safe_next_url(self):
        next_url = (self.request.POST.get("next") or self.request.GET.get("next") or "").strip()
        if not next_url:
            return None
        if url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return next_url
        return None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["next"] = self._get_safe_next_url() or ""
        return ctx

    def get_success_url(self):
        return self._get_safe_next_url() or super().get_success_url()


class AddMedicalNoteView(LoginRequiredMixin, CreateView):
    model = MedicalNote
    form_class = MedicalNoteForm
    template_name = 'clinic/add_note.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        target_patient_id = self.kwargs.get('user_id')
        try:
            self.target_patient = CustomUser.objects.get(
                id=target_patient_id, 
                role=CustomUser.Role.PATIENT
            )
        except CustomUser.DoesNotExist:
            messages.error(request, 'You do not have access to this patient.')
            return self.handle_no_permission()
        
        if not request.user.can_view_patient(self.target_patient):
            messages.error(request, 'You do not have access to this patient.')
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['patient'] = self.target_patient
        return ctx

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.patient = self.target_patient
        log_action(self.request, "ADD_NOTE", f"Patient ID: {self.target_patient.id}")
        return super().form_valid(form)

    def get_success_url(self):
        if self.request.user.is_nurse():
            return reverse_lazy('clinic:nurse_dashboard')
        elif self.request.user.is_doctor():
            return reverse_lazy('clinic:doctor_dashboard')
        return reverse_lazy('home')

class NoteAuthorMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_nurse() or user.is_doctor())

class EditMedicalNoteView(NoteAuthorMixin, UpdateView):
    model = MedicalNote
    form_class = MedicalNoteForm
    template_name = 'clinic/edit_note.html'

    def get_queryset(self):
        return MedicalNote.objects.filter(author=self.request.user)

    def get_success_url(self):
        if self.request.user.is_nurse():
            return reverse_lazy('clinic:nurse_dashboard')
        elif self.request.user.is_doctor():
            return reverse_lazy('clinic:doctor_dashboard')
        return reverse_lazy('home')

    def form_valid(self, form):
        log_action(self.request, "EDIT_NOTE", f"Note ID: {self.object.id}")
        return super().form_valid(form)


class DeleteMedicalNoteView(NoteAuthorMixin, DeleteView):
    model = MedicalNote
    template_name = 'clinic/delete_note_confirm.html'

    def get_queryset(self):
        return MedicalNote.objects.filter(author=self.request.user)

    def get_success_url(self):
        if self.request.user.is_nurse():
            return reverse_lazy('clinic:nurse_dashboard')
        elif self.request.user.is_doctor():
            return reverse_lazy('clinic:doctor_dashboard')
        return reverse_lazy('home')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        log_action(request, "DELETE_NOTE", f"Note ID: {self.object.id}")
        return super().delete(request, *args, **kwargs)


class ManageStaffView(AdminRequiredMixin, ListView):
    model = CustomUser
    template_name = 'clinic/manage_staff.html'
    context_object_name = 'staff_users'

    def get_queryset(self):
        return CustomUser.objects.filter(role__in=[CustomUser.Role.DOCTOR, CustomUser.Role.NURSE])

class CreateStaffView(AdminRequiredMixin, CreateView):
    form_class = StaffCreationForm
    template_name = 'clinic/create_staff.html'
    success_url = reverse_lazy('clinic:manage_staff')

    def form_valid(self, form):
        log_action(self.request, "CREATE_STAFF", f"User: {form.instance.username}, Role: {form.instance.role}")
        return super().form_valid(form)

class ToggleStaffStatusView(AdminRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(
            CustomUser.objects.filter(role__in=[CustomUser.Role.DOCTOR, CustomUser.Role.NURSE]),
            pk=pk
        )
        
        user.is_active = not user.is_active
        user.save()
        log_action(request, "TOGGLE_STAFF_STATUS", f"User: {user.username}, Active: {user.is_active}")
        return redirect('clinic:manage_staff')

class DeleteStaffView(AdminRequiredMixin, DeleteView):
    model = CustomUser
    template_name = 'clinic/delete_staff_confirm.html'
    success_url = reverse_lazy('clinic:manage_staff')

    def get_queryset(self):
        return CustomUser.objects.filter(role__in=[CustomUser.Role.DOCTOR, CustomUser.Role.NURSE])

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if self.object.is_admin():
            messages.error(request, "Cannot delete admin.")
            return redirect('clinic:manage_staff')

        if request.user.pk == self.object.pk:
            messages.error(request, "You cannot delete your own account.")
            return redirect('clinic:manage_staff')

        username = self.object.username
        role = self.object.role
        user_id = self.object.pk

        log_action(
            request,
            "DELETE_USER",
            resource=f"User: {username}",
            details=f"Deleted staff account (id={user_id}, role={role})",
            user_obj=request.user,
        )
        messages.success(request, f"Deleted user '{username}'.")
        return super().post(request, *args, **kwargs)


class EditNurseAssignmentsView(AdminRequiredMixin, UpdateView):
    model = NurseProfile
    form_class = NurseAssignmentForm
    template_name = 'clinic/edit_nurse_assignments.html'
    success_url = reverse_lazy('clinic:manage_staff')
    def get_queryset(self):
        return NurseProfile.objects.filter(user__role=CustomUser.Role.NURSE).select_related('user')

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        user_pk = self.kwargs.get('pk')
        profile = queryset.filter(user__pk=user_pk).first()
        if not profile:
            user = get_object_or_404(CustomUser, pk=user_pk, role=CustomUser.Role.NURSE)
            profile, created = NurseProfile.objects.get_or_create(user=user)
        return profile

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nurse_user'] = self.object.user
        return ctx

    def form_valid(self, form):
        log_action(
            self.request, 
            "UPDATE_NURSE_ASSIGNMENTS", 
            f"Nurse: {self.object.user.username}",
            f"Assigned doctors: {', '.join([d.user.username for d in form.cleaned_data['assigned_doctors']])}"
        )
        messages.success(self.request, f"Updated doctor assignments for {self.object.user.username}.")
        return super().form_valid(form)

class AuditLogView(AdminRequiredMixin, ListView):
    model = AuditLog
    template_name = 'clinic/audit_logs.html'
    context_object_name = 'logs'
    paginate_by = 50
    
    def get_queryset(self):
        qs = AuditLog.objects.all()
        role = (self.request.GET.get('role') or '').strip()
        action = (self.request.GET.get('action') or '').strip()

        valid_roles = {choice[0] for choice in CustomUser.Role.choices}
        if role in valid_roles:
            qs = qs.filter(actor__role=role)

        if action:
            action = action[:64]
            qs = qs.filter(action__icontains=action)
        return qs



class ManagePatientsView(AdminRequiredMixin, ListView):
    model = CustomUser
    template_name = 'clinic/manage_patients.html'
    context_object_name = 'patients'
    paginate_by = 20
    def get_queryset(self):
        qs = CustomUser.objects.filter(role=CustomUser.Role.PATIENT).select_related('patient_profile')
        search = (self.request.GET.get('search') or '').strip()
        if search:
            search = search[:100]
            qs = qs.filter(Q(username__icontains=search))
        return qs.order_by('username')


class DeletePatientView(AdminRequiredMixin, DeleteView):
    model = CustomUser
    template_name = 'clinic/delete_patient_confirm.html'
    success_url = reverse_lazy('clinic:manage_patients')
    def get_queryset(self):
        return CustomUser.objects.filter(role=CustomUser.Role.PATIENT)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            ctx['patient_profile'] = self.object.patient_profile
        except PatientProfile.DoesNotExist:
            ctx['patient_profile'] = None
        ctx['appointment_count'] = Appointment.objects.filter(patient=self.object).count()
        ctx['note_count'] = MedicalNote.objects.filter(patient=self.object).count()
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if not self.object.is_patient():
            messages.error(request, "Cannot delete non-patient users from this view.")
            return redirect('clinic:manage_patients')

        username = self.object.username
        email = self.object.email
        user_id = self.object.pk

        log_action(
            request,
            "DELETE_USER",
            resource=f"Patient: {username}",
            details=f"Deleted patient account (id={user_id}, email={email})",
            user_obj=request.user,
        )
        
        messages.success(request, f"Patient account '{username}' has been deleted.")
        return super().post(request, *args, **kwargs)


class TogglePatientStatusView(AdminRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(
            CustomUser.objects.filter(role=CustomUser.Role.PATIENT),
            pk=pk
        )
        
        user.is_active = not user.is_active
        user.save()
        
        status = "activated" if user.is_active else "deactivated"
        log_action(request, "TOGGLE_PATIENT_STATUS", f"User: {user.username}, Active: {user.is_active}")
        messages.success(request, f"Patient '{user.username}' has been {status}.")
        return redirect('clinic:manage_patients')


class AdminOrDoctorRequiredMixin(RoleRequiredMixin):
    allowed_roles = [CustomUser.Role.ADMIN, CustomUser.Role.DOCTOR]

class PatientCreateView(AdminOrDoctorRequiredMixin, CreateView):
    form_class = PatientCreationForm
    template_name = 'clinic/create_patient.html'
    def get_success_url(self):
        if self.request.user.is_admin():
            return reverse_lazy('clinic:manage_patients')
        return reverse_lazy('clinic:doctor_dashboard')
    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(
            self.request, 
            "CREATE_PATIENT", 
            f"User: {form.instance.username}",
            f"Created by: {self.request.user.username} ({self.request.user.get_role_display()})"
        )
        messages.success(self.request, f"Patient account '{form.instance.username}' created successfully.")
        return response

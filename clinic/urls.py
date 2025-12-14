from django.urls import path
from . import views

app_name = 'clinic'

urlpatterns = [
    path('admin-dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('doctor-dashboard/', views.DoctorDashboardView.as_view(), name='doctor_dashboard'),
    path('nurse-dashboard/', views.NurseDashboardView.as_view(), name='nurse_dashboard'),
    path('patient-dashboard/', views.PatientDashboardView.as_view(), name='patient_dashboard'),

    path('book-appointment/', views.BookAppointmentView.as_view(), name='book_appointment'),
    path('edit-profile/', views.ProfileEditView.as_view(), name='edit_profile'),
    path('appointment/<int:pk>/cancel/', views.PatientCancelAppointmentView.as_view(), name='patient_cancel_appointment'),
    
    path('appointment/<int:pk>/update-status/', views.UpdateAppointmentStatusView.as_view(), name='update_appointment_status'),
    path('appointment/<int:pk>/diagnose/', views.AddDiagnosisView.as_view(), name='add_diagnosis'),
    path('appointment-history/', views.DoctorAppointmentHistoryView.as_view(), name='doctor_appointment_history'),

    path('patient/<int:user_id>/add-note/', views.AddMedicalNoteView.as_view(), name='add_medical_note'),
    path('note/<int:pk>/edit/', views.EditMedicalNoteView.as_view(), name='edit_medical_note'),
    path('note/<int:pk>/delete/', views.DeleteMedicalNoteView.as_view(), name='delete_medical_note'),

    path('manage-staff/', views.ManageStaffView.as_view(), name='manage_staff'),
    path('create-staff/', views.CreateStaffView.as_view(), name='create_staff'),
    path('staff/<int:pk>/toggle-status/', views.ToggleStaffStatusView.as_view(), name='toggle_staff_status'),
    path('staff/<int:pk>/delete/', views.DeleteStaffView.as_view(), name='delete_staff'),
    path('staff/<int:pk>/edit-assignments/', views.EditNurseAssignmentsView.as_view(), name='edit_nurse_assignments'),
    
    path('manage-patients/', views.ManagePatientsView.as_view(), name='manage_patients'),
    path('create-patient/', views.PatientCreateView.as_view(), name='create_patient'),
    path('patient/<int:pk>/delete/', views.DeletePatientView.as_view(), name='delete_patient'),
    path('patient/<int:pk>/toggle-status/', views.TogglePatientStatusView.as_view(), name='toggle_patient_status'),
    
    path('audit-logs/', views.AuditLogView.as_view(), name='audit_logs'),
    path('patients-overview/', views.AdminPatientListView.as_view(), name='admin_patient_list'),
    path('appointments-overview/', views.AdminAppointmentListView.as_view(), name='admin_appointment_list'),
]


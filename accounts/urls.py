from django.urls import path
from . import views
from . import views_template_editor

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('db/backup/', views.db_backup, name='db_backup'),
    path('db/restore/', views.db_restore, name='db_restore'),
    path('db/delete/', views.db_delete, name='db_delete'),
    path('add-school/', views.add_school, name='add_school'),
    path('select-school/', views.select_school, name='select_school'),
    path('school-entry/<int:school_id>/', views.school_entry, name='school_entry'),
    path('school-entry/<int:school_id>/session/', views.school_session, name='school_session'),
    path('school-entry/<int:school_id>/registration/', views.school_registration, name='school_registration'),
    path('school-entry/<int:school_id>/class-data/', views.school_class_data, name='school_class_data'),
    path('school-entry/<int:school_id>/reports/', views.school_reports, name='school_reports'),
    path('school-entry/<int:school_id>/reports/results/', views.school_report_results, name='school_report_results'),
    path('school-entry/<int:school_id>/reports/broadsheet-class/', views.school_report_broadsheet_class, name='school_report_broadsheet_class'),
    path('school-entry/<int:school_id>/reports/subject-champions/', views.school_report_subject_champions, name='school_report_subject_champions'),
    path('school-entry/<int:school_id>/reports/broadsheet-subject/', views.school_report_broadsheet_subject, name='school_report_broadsheet_subject'),
    path('school-entry/<int:school_id>/settings/', views.school_settings, name='school_settings'),
    path('school-entry/<int:school_id>/settings/school-details/', views.school_settings_details, name='school_settings_details'),
    path('school-entry/<int:school_id>/settings/headteacher/', views.school_settings_headteacher, name='school_settings_headteacher'),
    path('school-entry/<int:school_id>/settings/email/', views.school_settings_email, name='school_settings_email'),
    path('school-entry/<int:school_id>/settings/users/', views.school_settings_users, name='school_settings_users'),
    path('school-entry/<int:school_id>/class-data/subjects/', views.school_class_subjects, name='school_class_subjects'),
    path('school-entry/<int:school_id>/class-data/marks-scores/', views.school_class_marks_scores, name='school_class_marks_scores'),
    path('school-entry/<int:school_id>/class-data/attendance/', views.school_class_attendance, name='school_class_attendance'),
    path('school-entry/<int:school_id>/class-data/attributes-skills/', views.school_class_attributes, name='school_class_attributes'),
    path('school-entry/<int:school_id>/class-data/comments/<str:comment_type>/', views.school_class_comments, name='school_class_comments'),
    path('school-entry/<int:school_id>/template-editor/', views_template_editor.template_editor_view, name='school_template_editor'),
    path('school-entry/<int:school_id>/registration/term/', views.school_term_settings, name='school_term_settings'),
    path('school-entry/<int:school_id>/registration/teachers/', views.school_teachers, name='school_teachers'),
    path('school-entry/<int:school_id>/registration/classes/', views.school_class_registration, name='school_class_registration'),
    path('school-entry/<int:school_id>/registration/students/', views.school_students, name='school_students'),
    path('logout/', views.logout_view, name='logout'),
]

from django.urls import path
from . import views
from . import views_template_editor

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('login/teacher/', views.teacher_login_view, name='teacher_login'),
    path('login/student/', views.student_login_view, name='student_login'),
    path('db/backup/', views.db_backup, name='db_backup'),
    path('db/restore/', views.db_restore, name='db_restore'),
    path('db/delete/', views.db_delete, name='db_delete'),
    path('add-school/', views.add_school, name='add_school'),
    path('select-school/', views.select_school, name='select_school'),
    path('school-entry/<int:school_id>/', views.school_entry, name='school_entry'),
    path('school-entry/<int:school_id>/session/', views.school_session, name='school_session'),
    path('school-entry/<int:school_id>/registration/', views.school_registration, name='school_registration'),
    path('school-entry/<int:school_id>/template-editor/', views_template_editor.template_editor_view, name='school_template_editor'),
    path('school-entry/<int:school_id>/registration/term/', views.school_term_settings, name='school_term_settings'),
    path('school-entry/<int:school_id>/registration/teachers/', views.school_teachers, name='school_teachers'),
    path('school-entry/<int:school_id>/registration/classes/', views.school_class_registration, name='school_class_registration'),
    path('school-entry/<int:school_id>/registration/students/', views.school_students, name='school_students'),
    path('logout/', views.logout_view, name='logout'),
]

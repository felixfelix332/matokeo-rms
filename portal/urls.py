from django.urls import path
from django.shortcuts import redirect
from . import views, teacher_views, student_views

app_name = 'portal'

urlpatterns = [
    path('', lambda r: redirect('accounts:login'), name='home'),

    # Admin Portal
    path('dashboard/', views.dashboard, name='dashboard'),
    path('students/', views.student_list, name='students'),
    path('students/<int:pk>/', views.student_detail, name='student_detail'),
    path('scores/', views.scores_view, name='scores'),
    path('results/', views.results_view, name='results'),
    path('attendance/', views.attendance_view, name='attendance'),
    path('fees/', views.fees_view, name='fees'),
    path('analytics/', views.analytics_view, name='analytics'),

    # Teacher Portal
    path('teacher/', teacher_views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/class/<int:class_id>/', teacher_views.teacher_class_students, name='teacher_class_students'),
    path('teacher/scores/', teacher_views.teacher_scores, name='teacher_scores'),
    path('teacher/marks/', teacher_views.marks_entry_menu, name='marks_menu'),
    path('teacher/marks/sheet/', teacher_views.marks_entry_sheet, name='marks_sheet'),

    # Attendance
    path('teacher/attendance/', teacher_views.teacher_attendance, name='teacher_attendance'),

    # Class List CRUD
    path('teacher/class-list/', teacher_views.teacher_class_list, name='teacher_class_list'),
    path('teacher/students/add/', teacher_views.teacher_student_add, name='teacher_student_add'),
    path('teacher/students/<int:student_id>/edit/', teacher_views.teacher_student_edit, name='teacher_student_edit'),
    path('teacher/students/<int:student_id>/delete/', teacher_views.teacher_student_delete, name='teacher_student_delete'),

    # Remarks
    path('teacher/remarks/', teacher_views.teacher_remarks, name='teacher_remarks'),

    # Report Cards / Results
    path('teacher/results/', teacher_views.teacher_results, name='teacher_results'),
    path('teacher/results/generate/', teacher_views.teacher_generate_results, name='teacher_generate_results'),
    path('teacher/report-card/<int:student_id>/', teacher_views.teacher_report_card, name='teacher_report_card'),

    # Template Editor
    path('teacher/template-editor/', teacher_views.teacher_template_editor, name='teacher_template_editor'),

    # Analytics & Broadsheet
    path('teacher/analytics/', teacher_views.teacher_analytics, name='teacher_analytics'),
    path('teacher/broadsheet/', teacher_views.teacher_broadsheet, name='teacher_broadsheet'),

    # Announcements
    path('teacher/announcements/', teacher_views.teacher_announcements, name='teacher_announcements'),

    # Session
    path('teacher/term-settings/', teacher_views.term_settings, name='term_settings'),
    path('teacher/sessions/', teacher_views.session_manage, name='session_manage'),

    # Registration
    path('teacher/teachers/', teacher_views.teacher_list_view, name='teacher_list'),
    path('teacher/teachers/<int:teacher_id>/edit/', teacher_views.teacher_edit_view, name='teacher_edit'),
    path('teacher/classes/', teacher_views.class_manage, name='class_manage'),
    path('teacher/subjects/', teacher_views.subject_manage, name='subject_manage'),

    # Class Data
    path('teacher/attributes/', teacher_views.attributes_entry, name='attributes_entry'),
    path('teacher/comments/', teacher_views.comments_entry, name='comments_entry'),

    # Reports
    path('teacher/broadsheet-subject/', teacher_views.broadsheet_subject, name='broadsheet_subject'),
    path('teacher/subject-champions/', teacher_views.subject_champions, name='subject_champions'),

    # Settings
    path('teacher/school-settings/', teacher_views.school_settings, name='school_settings'),
    path('teacher/users/', teacher_views.user_manage, name='user_manage'),

    # Student Portal
    path('my-portal/', student_views.student_portal, name='student_portal'),
]

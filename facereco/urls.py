
from django.contrib import admin
from django.urls import path
from facereco import views
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from facereco.views import download_attendance_pdf

urlpatterns = [
    path("private-files/<str:file_kind>/<int:object_id>/", views.private_file, name="private_file"),
    path('', views.index, name ='index'),
    path('register', views.register, name='register'),
    path('login', views.login, name='login'),  
    path("student/forgot-password/", views.student_forgot_password, name="student_forgot_password"),
    path('userpanel/', views.userpanel, name='userpanel'),
    path("parent/register/", views.parent_register, name="parent_register"),
    path("parent/login/", views.parent_login, name="parent_login"),
    path("parent/dashboard/", views.parent_dashboard, name="parent_dashboard"),
    path(
        "parent/report-card/<int:student_link_id>/",
        views.parent_report_card,
        name="parent_report_card",
    ),
    path("parent/logout/", views.parent_logout, name="parent_logout"),
    path(
        "parent/forgot-password/",
        auth_views.PasswordResetView.as_view(
            form_class=views.ParentPasswordResetForm,
            template_name="parent_password_reset.html",
            email_template_name="parent_password_reset_email.html",
            subject_template_name="parent_password_reset_subject.txt",
            success_url=reverse_lazy("parent_password_reset_done"),
        ),
        name="parent_password_reset",
    ),
    path(
        "parent/forgot-password/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="parent_password_reset_done.html",
        ),
        name="parent_password_reset_done",
    ),
    path(
        "parent/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="parent_password_reset_confirm.html",
            success_url=reverse_lazy("parent_password_reset_complete"),
        ),
        name="parent_password_reset_confirm",
    ),
    path(
        "parent/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="parent_password_reset_complete.html",
        ),
        name="parent_password_reset_complete",
        
    ),
    path('leave/', views.leave_portal, name='leave_portal'),
    path('announcements/mark-read/', views.mark_announcements_read, name='mark_announcements_read'),
    path('userprofile/', views.userprofile, name='profile'),
    path('admin-login/', views.adminlogin, name='adminlogin'),
    
    path('adminpanel/',views.adminpanel,name='adminpanel'),
    path("teacher-leave-requests/", views.admin_teacher_leaves, name="admin_teacher_leaves"),
    path('live-attendance/', views.liveattendance, name='liveattendance'),
    path('recognize-attendance/',views.recognize_attendance,name='recognize_attendance'
),
    path('myattendance/', views.myattendance, name='myattendance'),
     path('download-attendance-pdf/', download_attendance_pdf, name='download_attendance_pdf'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path("attendance-summary/", views.attendance_summary, name="attendance_summary"),
    path("manage-students/", views.manage_students, name="manage_students"),
    path("edit-student/<int:student_id>/", views.edit_student, name="edit_student"),
    path("delete-student/<int:student_id>/", views.delete_student, name="delete_student"),
    path('student_search/', views.student_search, name='student_search'),
    path("subjects/", views.subjects, name="subjects"),

    path("subjects/add/",views.add_subject,name="add_subject"),
    path("subjects/<int:subject_id>/edit/",views.edit_subject, name="edit_subject"),
    path("subjects/<int:subject_id>/delete/",views.delete_subject,name="delete_subject"),
    
   path("teachers/",views.manage_teachers,name="manage_teachers"),
path("teachers/add/",views.add_teacher,name="add_teacher"),
path("teachers/<int:teacher_id>/update/",views.update_teacher,name="update_teacher"),
path("teachers/<int:teacher_id>/delete/",views.delete_teacher,name="delete_teacher"),
    path('timetable/', views.timetable, name='timetable'),
    path(
    "teacher/",
    views.teacherpanel,
    name="teacherpanel"
),

path(
    "teacher/tests/",
    views.teacher_tests,
    name="teacher_tests"
),

path(
    "teacher/leaves/",
    views.teacher_leaves,
    name="teacher_leaves"
),

path(
    "teacher/change-password/",
    views.teacher_change_password,
    name="teacher_change_password"
),

path(
    "teacher/subjects/",
    views.teacher_subjects,
    name="teacher_subjects"
),

path(
    "teacher/students/",
    views.teacher_students,
    name="teacher_students"
),

path(
    "teacher/attendance/",
    views.teacher_attendance,
    name="teacher_attendance"
),

path(
    "teacher/profile/",
    views.teacher_profile,
    name="teacher_profile"
),

path(
    "teacher/leave/",
    views.teacher_leave_portal,
    name="teacher_leave_portal"
),

path(
    "teacher/logout/",
    views.teacher_logout,
    name="teacher_logout"
),
]

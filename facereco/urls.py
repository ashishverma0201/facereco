
from django.contrib import admin
from django.urls import path
from facereco import views
from django.contrib.auth import views as auth_views
from facereco.views import download_attendance_pdf

urlpatterns = [
    path('', views.index, name ='index'),
    path('register', views.register, name='register'),
    path('login', views.login, name='login'),  
    path('userpanel/', views.userpanel, name='userpanel'),
    path('userprofile/', views.userprofile, name='profile'),
    path('admin-login/', views.adminlogin, name='adminlogin'),
    
    path('adminpanel/',views.adminpanel,name='adminpanel'),
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
    "teacher/logout/",
    views.teacher_logout,
    name="teacher_logout"
),
]

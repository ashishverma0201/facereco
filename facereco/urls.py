
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
    path('myattendance/', views.myattendance, name='myattendance'),
     path('download-attendance-pdf/', download_attendance_pdf, name='download_attendance_pdf'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path("attendance-summary/", views.attendance_summary, name="attendance_summary"),
    path("manage-students/", views.manage_students, name="manage_students"),
    path("edit-student/<int:student_id>/", views.edit_student, name="edit_student"),
    path("delete-student/<int:student_id>/", views.delete_student, name="delete_student"),
    path('student_search/', views.student_search, name='student_search'),
]

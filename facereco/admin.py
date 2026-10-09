from django.contrib import admin

from .models import Attendance, Register, Subject, TeacherProfile


@admin.register(Register)
class RegisterAdmin(admin.ModelAdmin):

    list_display = ("student_name", "roll_no", "branch", "semester", "user")

    search_fields = ("student_name", "roll_no", "user__username")

    list_filter = ("branch", "semester")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):

    search_fields = ("name",)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):

    list_display = ("student", "subject", "timestamp")

    list_filter = ("subject", "timestamp")

    search_fields = ("student__username", "subject__name")


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "employee_id",
        "branch",
        "phone",
        "is_active",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "employee_id",
        "phone",
    )

    list_filter = (
        "branch",
        "is_active",
    )

    filter_horizontal = ("subjects",)
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import (
    Attendance,
    AdminMFAProfile,
    CollegeHoliday,
    Homework,
    ParentProfile,
    ParentStudentLink,
    ParentTeacherMessage,
    ParentVerificationCode,
    Register,
    RoomInventory,
    Subject,
    TeacherProfile,
)


admin.site.unregister(User)


@admin.register(User)
class RestrictedRoleUserAdmin(UserAdmin):
    """Keep account-role changes and user deletion in superuser hands."""

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        restricted = {"is_staff", "is_superuser", "groups", "user_permissions"}
        safe_fieldsets = []
        for title, options in fieldsets:
            options = options.copy()
            options["fields"] = tuple(
                field for field in options.get("fields", ())
                if field not in restricted
            )
            if options["fields"]:
                safe_fieldsets.append((title, options))
        return safe_fieldsets

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(AdminMFAProfile)
class AdminMFAProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "enabled")
    list_filter = ("enabled",)
    search_fields = ("user__username", "user__email")


@admin.register(RoomInventory)
class RoomInventoryAdmin(admin.ModelAdmin):
    list_display = ("room_number", "room_type", "other_purpose", "other_label", "is_active")
    list_filter = ("room_type", "other_purpose", "is_active")
    search_fields = ("room_number",)


@admin.register(CollegeHoliday)
class CollegeHolidayAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "holiday_type", "approval_status", "applies_to_all")
    search_fields = ("name",)
    list_filter = ("holiday_type", "approval_status", "applies_to_all")


@admin.register(ParentProfile)
class ParentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    search_fields = ("user__email", "user__first_name")


@admin.register(ParentStudentLink)
class ParentStudentLinkAdmin(admin.ModelAdmin):
    list_display = ("parent", "student", "relationship", "linked_at")
    search_fields = ("parent__user__email", "student__student_name", "student__roll_no")
    list_filter = ("relationship", "student__branch", "student__semester")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ParentVerificationCode)
class ParentVerificationCodeAdmin(admin.ModelAdmin):
    list_display = ("student", "issued_by", "issued_at", "expires_at", "used_at", "is_active")
    search_fields = ("student__student_name", "student__roll_no")
    list_filter = ("is_active", "issued_at")
    readonly_fields = ("code_hash", "issued_at", "used_at")


@admin.register(Homework)
class HomeworkAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "teacher", "due_date", "created_at")
    search_fields = ("title", "subject__name", "teacher__user__username")
    list_filter = ("due_date", "subject__branch", "subject__semester")


@admin.register(ParentTeacherMessage)
class ParentTeacherMessageAdmin(admin.ModelAdmin):
    list_display = ("student_link", "teacher", "sender", "created_at")
    search_fields = ("student_link__student__roll_no", "student_link__parent__user__email", "message")
    list_filter = ("teacher", "created_at")


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

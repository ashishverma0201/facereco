from datetime import datetime
from zoneinfo import ZoneInfo
from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from .storage import PrivateUploadStorage
from .upload_validation import validate_homework_upload, validate_image_upload

private_upload_storage = PrivateUploadStorage()


def local_attendance_date():
    return datetime.now(ZoneInfo(settings.TIME_ZONE)).date()


class Register(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    student_name = models.CharField(max_length=100)

    roll_no = models.CharField(
        max_length=20,
        unique=True
    )

    semester = models.CharField(
        max_length=20
    )

    branch = models.CharField(
        max_length=50
    )

    face_image = models.ImageField(
        upload_to="face_images/",
        storage=private_upload_storage,
        validators=[validate_image_upload],
        null=True,
        blank=True
    )

    def __str__(self):
        return self.student_name


class LoginAttempt(models.Model):
    """Stores hashed throttling buckets without retaining login identifiers."""
    key = models.CharField(max_length=64, primary_key=True)
    failures = models.PositiveSmallIntegerField(default=0)
    window_started = models.DateTimeField(default=timezone.now)
    locked_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return "Authentication throttle bucket"


class AdminMFAProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="admin_mfa")
    enabled = models.BooleanField(default=False)

    def __str__(self):
        return f"Admin MFA: {self.user.get_username()} ({'enabled' if self.enabled else 'disabled'})"


class AdminLoginChallenge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="admin_login_challenges")
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Admin login challenge for {self.user.get_username()}"


class Subject(models.Model):

    SEMESTER_CHOICES = [
        ("1", "1st Semester"),
        ("2", "2nd Semester"),
        ("3", "3rd Semester"),
        ("4", "4th Semester"),
        ("5", "5th Semester"),
        ("6", "6th Semester"),
        ("7", "7th Semester"),
        ("8", "8th Semester"),
    ]

    name = models.CharField(
        max_length=100
    )

    semester = models.CharField(
        max_length=2,
        choices=SEMESTER_CHOICES,
        default="1"
    )

    branch = models.CharField(
        max_length=50,
        default="IT"
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["semester", "branch", "name"]

        constraints = [
            models.UniqueConstraint(
                fields=["name", "semester", "branch"],
                name="unique_subject_per_semester_branch"
            )
        ]

    def __str__(self):
        return f"{self.name} - Sem {self.semester} - {self.branch}"
    

class Attendance(models.Model):

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE
    )

    timestamp = models.DateTimeField(
        auto_now_add=True
    )

    attendance_date = models.DateField(
        default=local_attendance_date,
        editable=False,
        null=True,
    )

    face_image = models.ImageField(
        upload_to="attendance_faces/",
        storage=private_upload_storage,
        validators=[validate_image_upload],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject", "attendance_date"],
                name="unique_student_subject_attendance_day",
            )
        ]

    def __str__(self):

        return (
            f"{self.student.username} - "
            f"{self.subject.name} - "
            f"{self.timestamp}"
        )
        
class Branch(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
            
class TeacherProfile(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_profile"
    )

    employee_id = models.CharField(
        max_length=30,
        unique=True
    )

    phone = models.CharField(
        max_length=15,
        blank=True,
        null=True
    )

    branch = models.CharField(
        max_length=50
    )
    
    branches = models.ManyToManyField(
    Branch,
    blank=True,
    related_name="teachers"
)

    subjects = models.ManyToManyField(
        Subject,
        blank=True,
        related_name="assigned_teachers"
    )

    is_active = models.BooleanField(
        default=True
    )

    # New teacher must change password on first login
    must_change_password = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return (
            f"{self.user.get_full_name()} "
            f"({self.employee_id})"
        )


class Announcement(models.Model):
    class Audience(models.TextChoices):
        STUDENTS = "STUDENTS", "Students"
        TEACHERS = "TEACHERS", "Teachers"

    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="announcements",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_announcements",
    )
    title = models.CharField(max_length=150)
    message = models.TextField()
    audience = models.CharField(
        max_length=10,
        choices=Audience.choices,
        default=Audience.STUDENTS,
    )
    branch = models.CharField(max_length=50, blank=True, null=True)
    semester = models.CharField(
        max_length=2,
        choices=Subject.SEMESTER_CHOICES,
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class AnnouncementRead(models.Model):
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name="reads",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="announcement_reads",
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "user"],
                name="unique_announcement_read_per_user",
            )
        ]


class DashboardNoticeRead(models.Model):
    class NoticeType(models.TextChoices):
        TEST = "TEST", "Test notice"
        ADJUSTMENT = "ADJUSTMENT", "Timetable adjustment"
        HOMEWORK = "HOMEWORK", "Homework update"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="dashboard_notice_reads")
    notice_type = models.CharField(max_length=12, choices=NoticeType.choices)
    object_id = models.PositiveBigIntegerField()
    seen_updated_at = models.DateTimeField()
    read_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "notice_type", "object_id"],
                name="unique_dashboard_notice_read",
            )
        ]


class ClassTest(models.Model):
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="class_tests",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="class_tests",
    )
    title = models.CharField(max_length=150)
    test_date = models.DateField()
    max_marks = models.DecimalField(max_digits=7, decimal_places=2)
    units_topics = models.TextField(help_text="Units, chapters, or topics covered by the test.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-test_date", "subject__name"]

    def __str__(self):
        return f"{self.title} - {self.subject.name}"


class TestResult(models.Model):
    test = models.ForeignKey(
        ClassTest,
        on_delete=models.CASCADE,
        related_name="results",
    )
    student = models.ForeignKey(
        Register,
        on_delete=models.CASCADE,
        related_name="test_results",
    )
    marks_obtained = models.DecimalField(max_digits=7, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["test", "student"],
                name="unique_result_per_student_test",
            )
        ]

    def __str__(self):
        return f"{self.student.roll_no} - {self.test.title}: {self.marks_obtained}"


class LeaveApplication(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    student = models.ForeignKey(
        Register,
        on_delete=models.CASCADE,
        related_name="leave_applications",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="leave_applications",
    )
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="leave_applications",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    teacher_note = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"{self.student.roll_no} - {self.subject.name} ({self.status})"


class TeacherLeaveApplication(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="own_leave_applications",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    admin_note = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"{self.teacher.employee_id} ({self.status})"


class TeacherLeaveAdjustment(models.Model):
    class AdjustmentType(models.TextChoices):
        SUBSTITUTE = "SUBSTITUTE", "Substitute teacher"
        LIBRARY = "LIBRARY", "Library period"
        CUSTOM = "CUSTOM", "Other activity"

    leave_application = models.ForeignKey(
        TeacherLeaveApplication,
        on_delete=models.CASCADE,
        related_name="adjustments",
    )
    timetable_slot = models.ForeignKey(
        "TimetableSlot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leave_adjustments",
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    original_teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.PROTECT,
        related_name="original_leave_adjustments",
    )
    class_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True)
    adjustment_type = models.CharField(
        max_length=12,
        choices=AdjustmentType.choices,
        default=AdjustmentType.LIBRARY,
    )
    substitute_teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="substitute_leave_adjustments",
    )
    custom_activity = models.CharField(max_length=150, blank=True)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["class_date", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["timetable_slot", "class_date"],
                name="unique_leave_adjustment_per_class_date",
            )
        ]

    def __str__(self):
        return f"{self.subject.name} on {self.class_date}"


from django.core.exceptions import ValidationError


class TimetableConfiguration(models.Model):
    academic_year = models.CharField(max_length=9)
    branch = models.CharField(max_length=50)
    semester = models.CharField(max_length=2, choices=Subject.SEMESTER_CHOICES)

    college_start = models.TimeField()
    college_end = models.TimeField()
    lunch_start = models.TimeField()
    lunch_end = models.TimeField()

    working_days = models.PositiveSmallIntegerField(default=6)
    default_theory_duration = models.PositiveSmallIntegerField(default=50)
    theory_rooms = models.CharField(
    max_length=255,
    default="204,205,208",
    help_text="Comma-separated theory classroom numbers"
)

    lab_rooms = models.CharField(
    max_length=255,
    default="Lab 1,Lab 2",
    help_text="Comma-separated practical lab room numbers"
)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "branch", "semester"],
                name="unique_timetable_configuration",
            )
        ]

    def __str__(self):
        return f"{self.academic_year} - {self.branch} - Sem {self.semester}"


class RoomInventory(models.Model):
    class RoomType(models.TextChoices):
        THEORY = "THEORY", "Theory classroom"
        LAB = "LAB", "Lab"
        OTHER = "OTHER", "Other facility"

    class OtherPurpose(models.TextChoices):
        LIBRARY = "LIBRARY", "Library"
        SPORTS = "SPORTS", "Sports room / court"
        OTHER = "OTHER", "Other"

    room_number = models.CharField(max_length=50, unique=True)
    room_type = models.CharField(max_length=10, choices=RoomType.choices)
    other_purpose = models.CharField(
        max_length=12,
        choices=OtherPurpose.choices,
        blank=True,
    )
    other_label = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["room_type", "room_number"]

    def clean(self):
        super().clean()
        if self.room_type == self.RoomType.OTHER and not self.other_purpose:
            raise ValidationError("Choose what this other room is used for.")
        if (
            self.room_type == self.RoomType.OTHER
            and self.other_purpose == self.OtherPurpose.OTHER
            and not self.other_label.strip()
        ):
            raise ValidationError({"other_label": "Name this other facility."})
        if self.room_type != self.RoomType.OTHER:
            self.other_purpose = ""
            self.other_label = ""
        elif self.other_purpose != self.OtherPurpose.OTHER:
            self.other_label = ""
        duplicate_rooms = RoomInventory.objects.filter(
            room_number__iexact=self.room_number.strip(),
        )
        if self.pk:
            duplicate_rooms = duplicate_rooms.exclude(pk=self.pk)
        if duplicate_rooms.exists():
            raise ValidationError({"room_number": "This room number is already in the inventory."})

    def __str__(self):
        if self.room_type == self.RoomType.OTHER:
            if self.other_purpose == self.OtherPurpose.OTHER and self.other_label:
                return f"{self.other_label} - {self.room_number}"
            return f"{self.get_other_purpose_display()} - {self.room_number}"
        return f"{self.get_room_type_display()} - {self.room_number}"


class SubjectScheduleRequirement(models.Model):
    subject = models.OneToOneField(
        Subject,
        on_delete=models.CASCADE,
        related_name="schedule_requirement",
    )
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.PROTECT,
        related_name="schedule_requirements",
    )

    theory_classes_per_week = models.PositiveSmallIntegerField(default=0)
    theory_duration_minutes = models.PositiveSmallIntegerField(default=50)

    lab_classes_per_week = models.PositiveSmallIntegerField(default=0)
    lab_duration_minutes = models.PositiveSmallIntegerField(
        default=120,
        help_text="Duration of each lab session in minutes.",
    )

    def clean(self):
        super().clean()

        if self.theory_classes_per_week == 0 and self.lab_classes_per_week == 0:
            raise ValidationError(
                "At least one theory class or lab class per week is required."
            )

        if self.theory_classes_per_week > 0 and self.theory_duration_minutes <= 0:
            raise ValidationError("Theory duration must be greater than zero.")

        if self.lab_classes_per_week > 0 and self.lab_duration_minutes <= 0:
            raise ValidationError("Lab duration must be greater than zero.")

        if self.subject_id and self.teacher_id:
            if not self.teacher.is_active:
                raise ValidationError("The selected teacher is inactive.")

            if not self.teacher.subjects.filter(pk=self.subject_id).exists():
                raise ValidationError(
                    "This teacher is not assigned to the selected subject."
                )

            if not self.teacher.branches.filter(
               name=self.subject.branch
                 ).exists():
                   raise ValidationError(
        "Teacher and subject must belong to the same branch."
    )

    def __str__(self):
        return f"{self.subject.name} - Weekly Schedule Requirements"


class CollegeHoliday(models.Model):
    class HolidayType(models.TextChoices):
        NATIONAL = "NATIONAL", "National Holiday"
        STATE = "STATE", "State Holiday"
        RESTRICTED = "RESTRICTED", "Restricted Holiday"
        COLLEGE = "COLLEGE", "College Holiday"
        VACATION = "VACATION", "Vacation"
        EXAM = "EXAM", "Examination"

    class ApprovalStatus(models.TextChoices):
        PENDING = "PENDING", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    name = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField()

    holiday_type = models.CharField(
        max_length=15,
        choices=HolidayType.choices,
    )

    source_url = models.URLField(blank=True)
    approval_status = models.CharField(
        max_length=10,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )

    applies_to_all = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()

        if self.end_date < self.start_date:
            raise ValidationError("End date cannot be before start date.")

    def __str__(self):
        return f"{self.name} ({self.start_date})"


class TimetableSlot(models.Model):
    class Day(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    class SessionType(models.TextChoices):
        THEORY = "THEORY", "Theory"
        LAB = "LAB", "Practical / Lab"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    configuration = models.ForeignKey(
        TimetableConfiguration,
        on_delete=models.CASCADE,
        related_name="slots",
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT)

    day = models.PositiveSmallIntegerField(choices=Day.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    session_type = models.CharField(
        max_length=10,
        choices=SessionType.choices,
    )
    room = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    def clean(self):
        super().clean()

        if self.end_time <= self.start_time:
            raise ValidationError("End time must be later than start time.")

        if self.subject_id and self.configuration_id:
            if (
                self.subject.branch != self.configuration.branch
                or self.subject.semester != self.configuration.semester
                or not self.subject.is_active
            ):
                raise ValidationError(
                    "Subject must be active and match the timetable branch and semester."
                )

        if self.teacher_id and self.subject_id:
            if not self.teacher.is_active:
                raise ValidationError("The selected teacher is inactive.")

            if not self.teacher.subjects.filter(pk=self.subject_id).exists():
                raise ValidationError(
                    "The teacher must be assigned to this subject."
                )

    def __str__(self):
        return f"{self.subject.name} - {self.get_day_display()}"


class ParentProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="parent_profile",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.email


class ParentStudentLink(models.Model):
    class Relationship(models.TextChoices):
        FATHER = "FATHER", "Father"
        MOTHER = "MOTHER", "Mother"
        GUARDIAN = "GUARDIAN", "Guardian"

    parent = models.ForeignKey(
        ParentProfile,
        on_delete=models.CASCADE,
        related_name="student_links",
    )
    student = models.ForeignKey(
        Register,
        on_delete=models.CASCADE,
        related_name="parent_links",
    )
    relationship = models.CharField(max_length=10, choices=Relationship.choices)
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student"],
                name="unique_parent_student_link",
            )
        ]

    def __str__(self):
        return f"{self.parent} - {self.student} ({self.get_relationship_display()})"


class ParentVerificationCode(models.Model):
    student = models.ForeignKey(
        Register,
        on_delete=models.CASCADE,
        related_name="parent_verification_codes",
    )
    code_hash = models.CharField(max_length=128)
    issued_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="issued_parent_codes",
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return f"Parent code for {self.student.roll_no}"


class Homework(models.Model):
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="homework_posts",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="homework_posts",
    )
    title = models.CharField(max_length=180)
    instructions = models.TextField()
    due_date = models.DateField()
    attachment = models.FileField(
        upload_to="homework/",
        storage=private_upload_storage,
        blank=True,
        validators=[validate_homework_upload],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "-created_at"]

    def __str__(self):
        return f"{self.subject.name}: {self.title}"


class ParentTeacherMessage(models.Model):
    student_link = models.ForeignKey(
        ParentStudentLink,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="parent_messages",
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="parent_teacher_messages",
    )
    message = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Message about {self.student_link.student.roll_no} to {self.teacher}"

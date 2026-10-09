from django.db import models
from django.contrib.auth.models import User


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
        null=True,
        blank=True
    )

    def __str__(self):
        return self.student_name


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

    face_image = models.ImageField(
        upload_to="attendance_faces/"
    )

    def __str__(self):

        return (
            f"{self.student.username} - "
            f"{self.subject.name} - "
            f"{self.timestamp}"
        )
        
        
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
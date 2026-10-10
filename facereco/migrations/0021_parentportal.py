import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("facereco", "0020_dashboardnoticeread"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ParentProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="parent_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="ParentStudentLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("relationship", models.CharField(choices=[("FATHER", "Father"), ("MOTHER", "Mother"), ("GUARDIAN", "Guardian")], max_length=10)),
                ("linked_at", models.DateTimeField(auto_now_add=True)),
                ("parent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="student_links", to="facereco.parentprofile")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="parent_links", to="facereco.register")),
            ],
        ),
        migrations.CreateModel(
            name="ParentVerificationCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code_hash", models.CharField(max_length=128)),
                ("issued_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("issued_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="issued_parent_codes", to=settings.AUTH_USER_MODEL)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="parent_verification_codes", to="facereco.register")),
            ],
            options={"ordering": ["-issued_at"]},
        ),
        migrations.CreateModel(
            name="Homework",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=180)),
                ("instructions", models.TextField()),
                ("due_date", models.DateField()),
                ("attachment", models.FileField(blank=True, upload_to="homework/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="homework_posts", to="facereco.subject")),
                ("teacher", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="homework_posts", to="facereco.teacherprofile")),
            ],
            options={"ordering": ["due_date", "-created_at"]},
        ),
        migrations.CreateModel(
            name="ParentTeacherMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.TextField(max_length=4000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("sender", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="parent_teacher_messages", to=settings.AUTH_USER_MODEL)),
                ("student_link", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="facereco.parentstudentlink")),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="parent_messages", to="facereco.teacherprofile")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddConstraint(
            model_name="parentstudentlink",
            constraint=models.UniqueConstraint(fields=("parent", "student"), name="unique_parent_student_link"),
        ),
    ]

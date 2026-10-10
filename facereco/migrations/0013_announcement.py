from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("facereco", "0012_branch_teacherprofile_branches"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Announcement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=150)),
                ("message", models.TextField()),
                ("branch", models.CharField(max_length=50)),
                ("semester", models.CharField(choices=[("1", "1st Semester"), ("2", "2nd Semester"), ("3", "3rd Semester"), ("4", "4th Semester"), ("5", "5th Semester"), ("6", "6th Semester"), ("7", "7th Semester"), ("8", "8th Semester")], max_length=2)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="announcements", to="facereco.teacherprofile")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]

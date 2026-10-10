from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("facereco", "0013_announcement"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="announcement",
            name="teacher",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="announcements",
                to="facereco.teacherprofile",
            ),
        ),
        migrations.AlterField(
            model_name="announcement",
            name="branch",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name="announcement",
            name="semester",
            field=models.CharField(
                blank=True,
                choices=[("1", "1st Semester"), ("2", "2nd Semester"), ("3", "3rd Semester"), ("4", "4th Semester"), ("5", "5th Semester"), ("6", "6th Semester"), ("7", "7th Semester"), ("8", "8th Semester")],
                max_length=2,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="announcement",
            name="audience",
            field=models.CharField(
                choices=[("STUDENTS", "Students"), ("TEACHERS", "Teachers")],
                default="STUDENTS",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="announcement",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_announcements",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

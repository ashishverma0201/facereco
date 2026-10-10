from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("facereco", "0016_classtest_testresult"),
    ]

    operations = [
        migrations.CreateModel(
            name="LeaveApplication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("reason", models.TextField()),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")], default="PENDING", max_length=10)),
                ("teacher_note", models.TextField(blank=True)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="leave_applications", to="facereco.register")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="leave_applications", to="facereco.subject")),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="leave_applications", to="facereco.teacherprofile")),
            ],
            options={"ordering": ["-requested_at"]},
        ),
    ]

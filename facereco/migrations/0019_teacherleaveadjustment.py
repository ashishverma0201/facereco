from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("facereco", "0018_teacherleaveapplication"),
    ]

    operations = [
        migrations.CreateModel(
            name="TeacherLeaveAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("class_date", models.DateField()),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField()),
                ("room", models.CharField(blank=True, max_length=50)),
                ("adjustment_type", models.CharField(choices=[("SUBSTITUTE", "Substitute teacher"), ("LIBRARY", "Library period"), ("CUSTOM", "Other activity")], default="LIBRARY", max_length=12)),
                ("custom_activity", models.CharField(blank=True, max_length=150)),
                ("admin_note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("leave_application", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="adjustments", to="facereco.teacherleaveapplication")),
                ("original_teacher", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="original_leave_adjustments", to="facereco.teacherprofile")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="facereco.subject")),
                ("substitute_teacher", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="substitute_leave_adjustments", to="facereco.teacherprofile")),
                ("timetable_slot", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="leave_adjustments", to="facereco.timetableslot")),
            ],
            options={"ordering": ["class_date", "start_time"]},
        ),
        migrations.AddConstraint(
            model_name="teacherleaveadjustment",
            constraint=models.UniqueConstraint(fields=("timetable_slot", "class_date"), name="unique_leave_adjustment_per_class_date"),
        ),
    ]

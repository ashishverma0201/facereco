from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("facereco", "0015_announcementread"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassTest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=150)),
                ("test_date", models.DateField()),
                ("max_marks", models.DecimalField(decimal_places=2, max_digits=7)),
                ("units_topics", models.TextField(help_text="Units, chapters, or topics covered by the test.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="class_tests", to="facereco.subject")),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="class_tests", to="facereco.teacherprofile")),
            ],
            options={"ordering": ["-test_date", "subject__name"]},
        ),
        migrations.CreateModel(
            name="TestResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("marks_obtained", models.DecimalField(decimal_places=2, max_digits=7)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="test_results", to="facereco.register")),
                ("test", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="results", to="facereco.classtest")),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("test", "student"), name="unique_result_per_student_test"),
                ],
            },
        ),
    ]

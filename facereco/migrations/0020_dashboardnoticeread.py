import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("facereco", "0019_teacherleaveadjustment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DashboardNoticeRead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notice_type", models.CharField(choices=[("TEST", "Test notice"), ("ADJUSTMENT", "Timetable adjustment")], max_length=12)),
                ("object_id", models.PositiveBigIntegerField()),
                ("seen_updated_at", models.DateTimeField()),
                ("read_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dashboard_notice_reads", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="dashboardnoticeread",
            constraint=models.UniqueConstraint(fields=("user", "notice_type", "object_id"), name="unique_dashboard_notice_read"),
        ),
    ]

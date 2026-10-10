from django.db import migrations, models
from django.db.models import Count
from django.utils import timezone
import facereco.models


def backfill_attendance_date(apps, schema_editor):
    Attendance = apps.get_model("facereco", "Attendance")
    database = schema_editor.connection.alias
    rows = Attendance.objects.using(database).only("pk", "timestamp").iterator()
    for row in rows:
        timestamp = row.timestamp
        attendance_date = (
            timezone.localtime(timestamp).date()
            if timezone.is_aware(timestamp)
            else timestamp.date()
        )
        Attendance.objects.using(database).filter(pk=row.pk).update(
            attendance_date=attendance_date,
        )

    duplicate_groups = list(
        Attendance.objects.using(database)
        .values("student_id", "subject_id", "attendance_date")
        .annotate(record_count=Count("pk"))
        .filter(record_count__gt=1)
    )
    for group in duplicate_groups:
        duplicate_ids = list(
            Attendance.objects.using(database)
            .filter(
                student_id=group["student_id"],
                subject_id=group["subject_id"],
                attendance_date=group["attendance_date"],
            )
            .order_by("timestamp", "pk")
            .values_list("pk", flat=True)[1:]
        )
        Attendance.objects.using(database).filter(pk__in=duplicate_ids).update(
            attendance_date=None,
        )


class Migration(migrations.Migration):

    dependencies = [("facereco", "0027_private_upload_storage")]

    operations = [
        migrations.AddField(
            model_name="attendance",
            name="attendance_date",
            field=models.DateField(editable=False, null=True),
        ),
        migrations.RunPython(backfill_attendance_date, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="attendance",
            name="attendance_date",
            field=models.DateField(
                default=facereco.models.local_attendance_date,
                editable=False,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="attendance",
            constraint=models.UniqueConstraint(
                fields=("student", "subject", "attendance_date"),
                name="unique_student_subject_attendance_day",
            ),
        ),
    ]

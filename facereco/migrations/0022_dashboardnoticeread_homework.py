from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("facereco", "0021_parentportal"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dashboardnoticeread",
            name="notice_type",
            field=models.CharField(
                choices=[
                    ("TEST", "Test notice"),
                    ("ADJUSTMENT", "Timetable adjustment"),
                    ("HOMEWORK", "Homework update"),
                ],
                max_length=12,
            ),
        ),
    ]

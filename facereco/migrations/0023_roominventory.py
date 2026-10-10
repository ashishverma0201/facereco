from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("facereco", "0022_dashboardnoticeread_homework"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoomInventory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("room_number", models.CharField(max_length=50, unique=True)),
                ("room_type", models.CharField(choices=[("THEORY", "Theory classroom"), ("LAB", "Lab"), ("OTHER", "Other facility")], max_length=10)),
                ("other_purpose", models.CharField(blank=True, choices=[("LIBRARY", "Library"), ("SPORTS", "Sports room / court"), ("OTHER", "Other")], max_length=12)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["room_type", "room_number"]},
        ),
    ]

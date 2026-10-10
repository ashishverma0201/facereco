from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("facereco", "0023_roominventory"),
    ]

    operations = [
        migrations.AddField(
            model_name="roominventory",
            name="other_label",
            field=models.CharField(blank=True, max_length=50),
        ),
    ]

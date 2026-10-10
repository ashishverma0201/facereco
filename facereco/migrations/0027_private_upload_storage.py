import facereco.storage
import facereco.upload_validation
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("facereco", "0026_adminmfa")]

    operations = [
        migrations.AlterField(
            model_name="register",
            name="face_image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="face_images/",
                storage=facereco.storage.PrivateUploadStorage(),
                validators=[facereco.upload_validation.validate_image_upload],
            ),
        ),
        migrations.AlterField(
            model_name="attendance",
            name="face_image",
            field=models.ImageField(
                upload_to="attendance_faces/",
                storage=facereco.storage.PrivateUploadStorage(),
                validators=[facereco.upload_validation.validate_image_upload],
            ),
        ),
        migrations.AlterField(
            model_name="homework",
            name="attachment",
            field=models.FileField(
                blank=True,
                upload_to="homework/",
                storage=facereco.storage.PrivateUploadStorage(),
                validators=[facereco.upload_validation.validate_homework_upload],
            ),
        ),
    ]

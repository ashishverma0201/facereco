
from django.db import migrations, models


def copy_existing_teacher_branches(apps, schema_editor):
    Branch = apps.get_model("facereco", "Branch")
    TeacherProfile = apps.get_model("facereco", "TeacherProfile")

    database = schema_editor.connection.alias

    for teacher in TeacherProfile.objects.using(database).all():
        branch_name = (teacher.branch or "").strip()

        if branch_name:
            branch, created = Branch.objects.using(database).get_or_create(
                name=branch_name
            )
            teacher.branches.add(branch)


class Migration(migrations.Migration):

    dependencies = [
        ("facereco", "0011_timetableconfiguration_lab_rooms_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Branch",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=50, unique=True)),
            ],
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="branches",
            field=models.ManyToManyField(
                blank=True,
                related_name="teachers",
                to="facereco.branch",
            ),
        ),
        migrations.RunPython(
            copy_existing_teacher_branches,
            migrations.RunPython.noop,
        ),
    ]
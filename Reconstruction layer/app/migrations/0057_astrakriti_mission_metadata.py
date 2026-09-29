import django.contrib.postgres.fields.jsonb
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("app", "0056_astrakriti_legacy_link")]

    operations = [
        migrations.CreateModel(
            name="AstrakritiMissionMetadata",
            fields=[
                (
                    "location",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "capture_context",
                    models.TextField(blank=True, default=""),
                ),
                (
                    "provenance",
                    django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict),
                ),
                ("schema_revision", models.PositiveSmallIntegerField(default=1)),
                (
                    "created_at",
                    models.DateTimeField(default=django.utils.timezone.now, editable=False),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "project",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="astrakriti_mission_metadata",
                        serialize=False,
                        to="app.project",
                    ),
                ),
            ],
            options={
                "verbose_name": "Astrakriti Mission metadata",
                "verbose_name_plural": "Astrakriti Mission metadata",
            },
        ),
    ]

import uuid

import django.contrib.postgres.fields.jsonb
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0052_grid_shift_correction"),
    ]

    operations = [
        migrations.CreateModel(
            name="AstrakritiMeasurement",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "name",
                    models.CharField(max_length=160),
                ),
                (
                    "measurement_type",
                    models.CharField(
                        choices=[
                            ("distance", "Distance"),
                            ("area", "Area"),
                            ("volume", "DSM volume"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "geometry",
                    django.contrib.postgres.fields.jsonb.JSONField(default=dict),
                ),
                (
                    "result",
                    django.contrib.postgres.fields.jsonb.JSONField(
                        blank=True,
                        default=dict,
                    ),
                ),
                (
                    "units",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "crs",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "method",
                    models.CharField(blank=True, default="", max_length=160),
                ),
                (
                    "source_artifact_revision",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                (
                    "schema_revision",
                    models.PositiveSmallIntegerField(default=1),
                ),
                (
                    "created_at",
                    models.DateTimeField(default=django.utils.timezone.now, editable=False),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "author",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="astrakriti_measurements",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="astrakriti_measurements",
                        to="app.project",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="astrakriti_measurements",
                        to="app.task",
                    ),
                ),
            ],
            options={
                "verbose_name": "Astrakriti measurement",
                "verbose_name_plural": "Astrakriti measurements",
                "ordering": ("-updated_at", "-created_at"),
            },
        ),
        migrations.AddIndex(
            model_name="astrakritimeasurement",
            index=models.Index(fields=["task", "updated_at"], name="app_astra_task_upd_0e7348_idx"),
        ),
        migrations.AddIndex(
            model_name="astrakritimeasurement",
            index=models.Index(fields=["project", "updated_at"], name="app_astra_proj_upd_6a4c95_idx"),
        ),
    ]

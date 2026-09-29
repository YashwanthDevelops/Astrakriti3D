import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0053_astrakriti_measurement"),
    ]

    operations = [
        migrations.CreateModel(
            name="AstrakritiSubmission",
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
                    "idempotency_key",
                    models.CharField(max_length=128, unique=True),
                ),
                ("request_fingerprint", models.CharField(max_length=128)),
                ("task_name", models.CharField(max_length=255)),
                ("state", models.CharField(default="reserved", max_length=24)),
                (
                    "created_at",
                    models.DateTimeField(default=django.utils.timezone.now, editable=False),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="astrakriti_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="astrakriti_submissions",
                        to="app.project",
                    ),
                ),
                (
                    "task",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="astrakriti_submission",
                        to="app.task",
                    ),
                ),
            ],
            options={
                "verbose_name": "Astrakriti submission",
                "verbose_name_plural": "Astrakriti submissions",
                "ordering": ("-updated_at", "-created_at"),
            },
        ),
        migrations.AddIndex(
            model_name="astrakritisubmission",
            index=models.Index(
                fields=["owner", "updated_at"],
                name="app_astra_sub_owner_9c0db3_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="astrakritisubmission",
            index=models.Index(
                fields=["project", "updated_at"],
                name="app_astra_sub_proj_5d9a3e_idx",
            ),
        ),
    ]

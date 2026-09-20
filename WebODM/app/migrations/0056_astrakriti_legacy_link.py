import uuid

import django.contrib.postgres.fields.jsonb
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0055_astrakriti_preparation"),
    ]

    operations = [
        migrations.CreateModel(
            name="AstrakritiLegacyLink",
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
                ("source_path", models.CharField(max_length=1024)),
                (
                    "entity_type",
                    models.CharField(
                        choices=[
                            ("mission", "Mission"),
                            ("run", "Run"),
                            ("job", "Job"),
                        ],
                        max_length=16,
                    ),
                ),
                ("legacy_id", models.CharField(max_length=255)),
                ("legacy_parent_id", models.CharField(blank=True, default="", max_length=255)),
                ("legacy_label", models.CharField(blank=True, default="", max_length=255)),
                ("legacy_status", models.CharField(blank=True, default="", max_length=64)),
                (
                    "mapping_state",
                    models.CharField(
                        choices=[
                            ("linked", "Linked"),
                            ("reconciliation_required", "Reconciliation required"),
                            ("conflict", "Conflict"),
                        ],
                        default="reconciliation_required",
                        max_length=32,
                    ),
                ),
                (
                    "legacy_payload",
                    django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict),
                ),
                (
                    "reconciliation",
                    django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict),
                ),
                (
                    "created_at",
                    models.DateTimeField(default=django.utils.timezone.now, editable=False),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="astrakriti_legacy_links",
                        to="app.project",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="astrakriti_legacy_links",
                        to="app.task",
                    ),
                ),
            ],
            options={
                "verbose_name": "Astrakriti legacy link",
                "verbose_name_plural": "Astrakriti legacy links",
                "ordering": ("source_path", "entity_type", "legacy_id"),
            },
        ),
        migrations.AddConstraint(
            model_name="astrakritilegacylink",
            constraint=models.UniqueConstraint(
                fields=("source_path", "entity_type", "legacy_id"),
                name="astrakriti_legacy_link_identity",
            ),
        ),
        migrations.AddIndex(
            model_name="astrakritilegacylink",
            index=models.Index(
                fields=["mapping_state", "updated_at"],
                name="app_astra_legacy_state_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="astrakritilegacylink",
            index=models.Index(
                fields=["project", "task"],
                name="app_astra_legacy_refs_idx",
            ),
        ),
    ]

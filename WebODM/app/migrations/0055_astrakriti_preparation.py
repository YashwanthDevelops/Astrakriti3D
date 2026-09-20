import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0054_astrakriti_submission"),
    ]

    operations = [
        migrations.AddField(
            model_name="astrakritisubmission",
            name="source_mode",
            field=models.CharField(blank=True, default="", max_length=24),
        ),
        migrations.AddField(
            model_name="astrakritisubmission",
            name="companion_job_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="astrakritisubmission",
            name="preparation_state",
            field=models.CharField(default="not_started", max_length=32),
        ),
        migrations.AddField(
            model_name="astrakritisubmission",
            name="preparation_metadata",
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict),
        ),
    ]

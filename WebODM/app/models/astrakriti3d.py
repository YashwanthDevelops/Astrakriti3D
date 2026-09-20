import uuid

from django.conf import settings
from django.contrib.postgres import fields
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AstrakritiMissionMetadata(models.Model):
    """Astrakriti-owned context for exactly one authoritative WebODM Project.

    Project.name and Project.description remain the sole writable authority
    for the Mission's display name and description.
    """

    project = models.OneToOneField(
        "Project",
        related_name="astrakriti_mission_metadata",
        on_delete=models.CASCADE,
        primary_key=True,
    )
    location = models.CharField(max_length=255, default="", blank=True)
    capture_context = models.TextField(default="", blank=True)
    provenance = fields.JSONField(default=dict, blank=True)
    schema_revision = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Astrakriti Mission metadata")
        verbose_name_plural = _("Astrakriti Mission metadata")


class AstrakritiMeasurement(models.Model):
    """Durable, task-scoped measurements owned by the WebODM database.

    Potree scene data remains the native authority for 3D scene persistence. This
    model is intentionally limited to measurements created from the Map
    workspace, where WebODM's existing measurement plugin has no durable store.
    """

    DISTANCE = "distance"
    AREA = "area"
    VOLUME = "volume"
    MEASUREMENT_TYPES = (
        (DISTANCE, _("Distance")),
        (AREA, _("Area")),
        (VOLUME, _("DSM volume")),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        "Task",
        related_name="astrakriti_measurements",
        on_delete=models.CASCADE,
    )
    project = models.ForeignKey(
        "Project",
        related_name="astrakriti_measurements",
        on_delete=models.CASCADE,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="astrakriti_measurements",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=160)
    measurement_type = models.CharField(max_length=16, choices=MEASUREMENT_TYPES)
    geometry = fields.JSONField(default=dict)
    result = fields.JSONField(default=dict, blank=True)
    units = models.CharField(max_length=64, default="", blank=True)
    crs = models.CharField(max_length=255, default="", blank=True)
    method = models.CharField(max_length=160, default="", blank=True)
    source_artifact_revision = models.CharField(max_length=128, default="", blank=True)
    schema_revision = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")
        indexes = [
            models.Index(fields=("task", "updated_at"), name="app_astra_task_upd_0e7348_idx"),
            models.Index(fields=("project", "updated_at"), name="app_astra_proj_upd_6a4c95_idx"),
        ]
        verbose_name = _("Astrakriti measurement")
        verbose_name_plural = _("Astrakriti measurements")

    def clean(self):
        if self.task_id and self.project_id:
            task_project_id = self.task.project_id
            if task_project_id != self.project_id:
                raise ValidationError({"project": _("The measurement project must match the task project.")})

    def __str__(self):
        return "{} ({})".format(self.name, self.measurement_type)


class AstrakritiSubmission(models.Model):
    """Durable idempotency record for the Astrakriti native intake.

    The browser may lose the response after WebODM has created a partial Task.
    Keeping the idempotency key and native identities in WebODM lets a retry
    reconcile that response instead of creating another Project or Task.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True)
    request_fingerprint = models.CharField(max_length=128)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="astrakriti_submissions",
        on_delete=models.PROTECT,
    )
    project = models.ForeignKey(
        "Project",
        related_name="astrakriti_submissions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    task = models.OneToOneField(
        "Task",
        related_name="astrakriti_submission",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    task_name = models.CharField(max_length=255)
    state = models.CharField(max_length=24, default="reserved")
    source_mode = models.CharField(max_length=24, default="", blank=True)
    companion_job_id = models.CharField(max_length=128, default="", blank=True)
    preparation_state = models.CharField(max_length=32, default="not_started")
    preparation_metadata = fields.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")
        indexes = [
            models.Index(fields=("owner", "updated_at"), name="app_astra_sub_owner_9c0db3_idx"),
            models.Index(fields=("project", "updated_at"), name="app_astra_sub_proj_5d9a3e_idx"),
        ]
        verbose_name = _("Astrakriti submission")
        verbose_name_plural = _("Astrakriti submissions")

    def clean(self):
        if self.task_id and self.project_id and self.task.project_id != self.project_id:
            raise ValidationError({"project": _("The submission project must match the task project.")})

    def __str__(self):
        return "{} ({})".format(self.task_name, self.idempotency_key)


class AstrakritiLegacyLink(models.Model):
    """Additive, auditable link for records from the legacy Astrakriti stores.

    The link keeps the legacy identity and source payload intact while making
    the native Project/Task association explicit.  Reconciliation never
    guesses by display name and never creates a native Project or Task.
    """

    MISSION = "mission"
    RUN = "run"
    JOB = "job"
    ENTITY_TYPES = (
        (MISSION, _("Mission")),
        (RUN, _("Run")),
        (JOB, _("Job")),
    )

    LINKED = "linked"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    CONFLICT = "conflict"
    LINK_STATES = (
        (LINKED, _("Linked")),
        (RECONCILIATION_REQUIRED, _("Reconciliation required")),
        (CONFLICT, _("Conflict")),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_path = models.CharField(max_length=1024)
    entity_type = models.CharField(max_length=16, choices=ENTITY_TYPES)
    legacy_id = models.CharField(max_length=255)
    legacy_parent_id = models.CharField(max_length=255, default="", blank=True)
    legacy_label = models.CharField(max_length=255, default="", blank=True)
    legacy_status = models.CharField(max_length=64, default="", blank=True)
    mapping_state = models.CharField(
        max_length=32,
        choices=LINK_STATES,
        default=RECONCILIATION_REQUIRED,
    )
    project = models.ForeignKey(
        "Project",
        related_name="astrakriti_legacy_links",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    task = models.ForeignKey(
        "Task",
        related_name="astrakriti_legacy_links",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    legacy_payload = fields.JSONField(default=dict, blank=True)
    reconciliation = fields.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("source_path", "entity_type", "legacy_id")
        constraints = [
            models.UniqueConstraint(
                fields=("source_path", "entity_type", "legacy_id"),
                name="astrakriti_legacy_link_identity",
            ),
        ]
        indexes = [
            models.Index(fields=("mapping_state", "updated_at"), name="app_astra_legacy_state_idx"),
            models.Index(fields=("project", "task"), name="app_astra_legacy_refs_idx"),
        ]
        verbose_name = _("Astrakriti legacy link")
        verbose_name_plural = _("Astrakriti legacy links")

    def clean(self):
        if self.task_id and self.project_id and self.task.project_id != self.project_id:
            raise ValidationError({"project": _("The link project must match the task project.")})
        if self.entity_type == self.MISSION and self.task_id:
            raise ValidationError({"task": _("A legacy Mission may only link to a WebODM Project.")})
        if self.mapping_state == self.LINKED:
            if self.entity_type == self.MISSION and not self.project_id:
                raise ValidationError({"project": _("A linked Mission requires a WebODM Project.")})
            if self.entity_type in (self.RUN, self.JOB) and not self.task_id:
                raise ValidationError({"task": _("A linked Run or Job requires a WebODM Task.")})

    def __str__(self):
        return "{}:{} ({})".format(self.entity_type, self.legacy_id, self.mapping_state)

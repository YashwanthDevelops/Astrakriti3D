import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import quote
import zipfile

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, serializers, status
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.api.common import check_project_perms
from app.api.tasks import TaskNestedView
from app.models import (
    AstrakritiLegacyLink,
    AstrakritiMeasurement,
    AstrakritiMissionMetadata,
    AstrakritiSubmission,
    Project,
    Task,
)
from worker import tasks as worker_tasks

from .companion import AstrakritiCompanionClient, CompanionError, CompanionNotConfigured
from .views import _health_payload, artifact_revision


PREPARATION_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")


def _positive_env_int(name, default):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(1, value)


PREPARATION_BUNDLE_MAX_MEMBERS = _positive_env_int(
    "ASTRAKRITI_PREPARATION_MAX_MEMBERS", 100000
)
PREPARATION_BUNDLE_MAX_UNCOMPRESSED_BYTES = _positive_env_int(
    "ASTRAKRITI_PREPARATION_MAX_UNCOMPRESSED_BYTES", 16 * 1024**3
)
PREPARATION_EVIDENCE_MAX_BYTES = _positive_env_int(
    "ASTRAKRITI_PREPARATION_EVIDENCE_MAX_BYTES", 64 * 1024**2
)
PREPARATION_EVIDENCE_SCHEMA = "astrakriti3d.preparation-review.v1"


def _stage_companion_upload(upload):
    """Copy an incoming upload to a readable request-owned file.

    Large multipart uploads use Django's ``TemporaryUploadedFile``. Its
    descriptor may already be closed by the time the server-side companion
    client builds its outbound multipart request, while the temporary path is
    still valid. Staging through the path (or the upload chunks for in-memory
    files) makes the handoff deterministic and keeps the browser upload
    lifecycle separate from the companion request lifecycle.
    """

    suffix = Path(str(getattr(upload, "name", ""))).suffix.lower() or ".upload"
    staging_root = Path(settings.MEDIA_TMP)
    staging_root.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix="astrakriti-companion-",
        suffix=suffix,
        dir=str(staging_root),
        delete=False,
    )
    path = Path(handle.name)
    try:
        source_path = None
        try:
            source_path = upload.temporary_file_path()
        except (AttributeError, NotImplementedError, OSError, ValueError):
            source_path = None

        if source_path:
            with Path(source_path).open("rb") as source:
                shutil.copyfileobj(source, handle)
        else:
            try:
                for chunk in upload.chunks():
                    handle.write(chunk)
            except (OSError, ValueError) as exc:
                raise serializers.ValidationError(
                    "The uploaded source could not be read."
                ) from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        handle.close()
    return path


class MeasurementPayloadSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False, allow_blank=False)
    measurement_type = serializers.ChoiceField(
        choices=["distance", "area", "volume"], required=False
    )
    geometry = serializers.JSONField(required=False)
    result = serializers.JSONField(required=False)
    units = serializers.CharField(max_length=64, required=False, allow_blank=True)
    crs = serializers.CharField(max_length=255, required=False, allow_blank=True)
    method = serializers.CharField(max_length=160, required=False, allow_blank=True)
    expected_updated_at = serializers.DateTimeField(required=False, write_only=True)


class IntakeReservationSerializer(serializers.Serializer):
    """Validate the non-file part of the native intake reservation."""

    idempotency_key = serializers.CharField(min_length=16, max_length=128)
    project_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    project_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    task_name = serializers.CharField(max_length=255, allow_blank=False)
    file_fingerprint = serializers.CharField(max_length=512, required=False, allow_blank=True)


class IntakeFrameSelectionSerializer(serializers.Serializer):
    strategy = serializers.ChoiceField(choices=("r1_all", "r2_advisory", "coverage_advisory", "manual"))
    selected_filenames = serializers.ListField(
        child=serializers.CharField(max_length=255, allow_blank=False),
        allow_empty=False,
        max_length=100000,
    )


class MissionMetadataSerializer(serializers.Serializer):
    location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    capture_context = serializers.CharField(required=False, allow_blank=True)
    provenance = serializers.JSONField(required=False)

    def validate_provenance(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Provenance must be a JSON object.")
        return value


class LegacyReconciliationView(APIView):
    """Expose a redacted, read-only reconciliation queue to WebODM staff."""

    permission_classes = (IsAdminUser,)

    def get(self, request):
        states = (
            AstrakritiLegacyLink.RECONCILIATION_REQUIRED,
            AstrakritiLegacyLink.CONFLICT,
        )
        queryset = AstrakritiLegacyLink.objects.filter(mapping_state__in=states)
        try:
            offset = max(0, int(request.query_params.get("offset", "0")))
            limit = min(100, max(1, int(request.query_params.get("limit", "50"))))
        except (TypeError, ValueError):
            raise serializers.ValidationError("Reconciliation pagination must use integer values.")

        counts = {
            row["mapping_state"]: row["count"]
            for row in queryset.values("mapping_state").annotate(count=Count("id"))
        }
        rows = queryset.order_by("updated_at", "id")[offset : offset + limit]
        items = []
        for link in rows:
            reconciliation = link.reconciliation if isinstance(link.reconciliation, dict) else {}
            reasons = reconciliation.get("reasons", [])
            if not isinstance(reasons, list):
                reasons = []
            items.append({
                "id": str(link.id),
                "entity_type": link.entity_type,
                "legacy_id": link.legacy_id,
                "legacy_label": link.legacy_label,
                "legacy_status": link.legacy_status,
                "mapping_state": link.mapping_state,
                "reasons": [str(reason)[:128] for reason in reasons[:20]],
                "project_id": str(link.project_id) if link.project_id else None,
                "task_id": str(link.task_id) if link.task_id else None,
                "updated_at": link.updated_at,
            })
        return Response({
            "count": queryset.count(),
            "counts": {
                "reconciliation_required": counts.get(AstrakritiLegacyLink.RECONCILIATION_REQUIRED, 0),
                "conflict": counts.get(AstrakritiLegacyLink.CONFLICT, 0),
            },
            "offset": offset,
            "limit": limit,
            "items": items,
        })


class SubmissionConflict(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _(
        "This idempotency key is already bound to a different reconstruction request."
    )
    default_code = "submission_conflict"


class CompanionUnavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = _("The Astrakriti preparation companion is unavailable.")
    default_code = "companion_unavailable"


class MeasurementConflict(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _(
        "This measurement changed in another editor. Reload the latest saved geometry before editing it again."
    )
    default_code = "measurement_conflict"


class MeasurementExportNegotiation(DefaultContentNegotiation):
    """Keep ``format=geojson`` as an export selector, not a DRF renderer."""

    def select_renderer(self, request, renderers, format_suffix=None):
        format_query_param = self.settings.URL_FORMAT_OVERRIDE
        original_query = request._request.GET
        if format_query_param and format_query_param in original_query:
            query = original_query.copy()
            query.pop(format_query_param, None)
            request._request.GET = query
            try:
                return super().select_renderer(request, renderers, format_suffix)
            finally:
                request._request.GET = original_query
        return super().select_renderer(request, renderers, format_suffix)


def _geometry_from_payload(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError("geometry must be a GeoJSON geometry or Feature")
    if value.get("type") == "Feature":
        value = value.get("geometry")
    if not isinstance(value, dict):
        raise serializers.ValidationError("GeoJSON Feature is missing geometry")

    geometry_type = value.get("type")
    if geometry_type not in ("LineString", "Polygon"):
        raise serializers.ValidationError("only LineString and Polygon measurements are supported")
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) == 0:
        raise serializers.ValidationError("geometry coordinates are required")

    def vertex(item):
        if not isinstance(item, (list, tuple)) or len(item) not in (2, 3):
            raise serializers.ValidationError("each coordinate must contain two or three numbers")
        if any(
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or not math.isfinite(number)
            for number in item
        ):
            raise serializers.ValidationError("geometry coordinates must be finite numbers")
        return list(item)

    if geometry_type == "LineString":
        if len(coordinates) < 2:
            raise serializers.ValidationError("a distance needs at least two vertices")
        coordinates = [vertex(item) for item in coordinates]
    else:
        rings = []
        for ring in coordinates:
            if not isinstance(ring, list) or len(ring) < 4:
                raise serializers.ValidationError("an area needs a closed polygon ring")
            vertices = [vertex(item) for item in ring]
            if vertices[0] != vertices[-1]:
                raise serializers.ValidationError("an area needs a closed polygon ring")
            rings.append(vertices)
        coordinates = rings
    return {"type": geometry_type, "coordinates": coordinates}


def _validate_payload(serializer_data, task, existing=None):
    data = dict(serializer_data)
    geometry_value = data.get("geometry")
    if geometry_value is None and existing is not None:
        geometry = existing.geometry
    else:
        geometry = _geometry_from_payload(geometry_value)

    measurement_type = data.get(
        "measurement_type", existing.measurement_type if existing is not None else None
    )
    if measurement_type is None:
        measurement_type = "distance" if geometry["type"] == "LineString" else "area"
    if measurement_type == "distance" and geometry["type"] != "LineString":
        raise serializers.ValidationError("distance measurements require a LineString")
    if measurement_type in ("area", "volume") and geometry["type"] != "Polygon":
        raise serializers.ValidationError("area and volume measurements require a Polygon")

    result = data.get("result", existing.result if existing is not None else {})
    if result is None:
        result = {}
    if not isinstance(result, dict):
        raise serializers.ValidationError("result must be an object")

    if measurement_type == "volume" and task.dsm_extent is None:
        raise serializers.ValidationError(
            "volume measurements require a task with a valid DSM extent"
        )

    return {
        "name": data.get("name", existing.name if existing is not None else "Measurement"),
        "measurement_type": measurement_type,
        "geometry": geometry,
        "result": result,
        "units": data.get("units", existing.units if existing is not None else ""),
        "crs": data.get(
            "crs", existing.crs if existing is not None else "EPSG:4326"
        ),
        "method": data.get(
            "method", existing.method if existing is not None else "WebODM map measurement"
        ),
    }


def _measurement_payload(measurement, task):
    current_revision = artifact_revision(task)
    return {
        "id": str(measurement.id),
        "task_id": str(measurement.task_id),
        "project_id": str(measurement.project_id),
        "name": measurement.name,
        "measurement_type": measurement.measurement_type,
        "geometry": measurement.geometry,
        "result": measurement.result,
        "units": measurement.units,
        "crs": measurement.crs,
        "method": measurement.method,
        "source_artifact_revision": measurement.source_artifact_revision,
        "stale": measurement.source_artifact_revision != current_revision,
        "schema_revision": measurement.schema_revision,
        "author_id": measurement.author_id,
        "created_at": measurement.created_at,
        "updated_at": measurement.updated_at,
    }


def _require_write_access(request, task):
    if not request.user.is_authenticated:
        raise exceptions.NotAuthenticated()
    if task.check_public_edit():
        check_project_perms(request, task.project, perms=("change_project",))


def _intake_request_fingerprint(data):
    material = {
        "project_id": data.get("project_id") or "",
        "project_name": data.get("project_name", "").strip(),
        "task_name": data["task_name"].strip(),
        "file_fingerprint": data.get("file_fingerprint", ""),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _intake_payload(submission, reused=False):
    task = submission.task
    project = submission.project
    return {
        "submission_id": str(submission.id),
        "idempotency_key": submission.idempotency_key,
        "project_id": str(project.id) if project is not None else None,
        "task_id": str(task.id) if task is not None else None,
        "task_partial": bool(task is not None and task.partial),
        "state": (
            "orphaned"
            if task is None
            else "reserved"
            if task.partial
            else "committed"
        ),
        "reused": reused,
    }


def _intake_project(request, data):
    project_id = data.get("project_id")
    if project_id:
        try:
            project = Project.objects.get(pk=project_id, deleting=False)
        except (ObjectDoesNotExist, DjangoValidationError, ValueError):
            raise exceptions.NotFound()
        check_project_perms(request, project, perms=("change_project",))
        return project

    if not request.user.has_perm("app.add_project"):
        raise exceptions.PermissionDenied()
    project_name = data.get("project_name", "").strip()
    if not project_name:
        raise serializers.ValidationError({"project_name": "A new Project name is required."})
    return Project.objects.create(
        owner=request.user,
        name=project_name,
        description="Astrakriti3D reconstruction Project",
    )


def _submission_for_write(request, submission_id):
    try:
        submission = AstrakritiSubmission.objects.select_related(
            "project", "task"
        ).get(pk=submission_id)
    except (AstrakritiSubmission.DoesNotExist, DjangoValidationError, ValueError):
        raise exceptions.NotFound()
    if submission.owner_id != request.user.id or submission.project is None:
        raise exceptions.NotFound()
    check_project_perms(request, submission.project, perms=("change_project",))
    if submission.task is None:
        raise SubmissionConflict(detail=_("The reserved WebODM Task is no longer available."))
    return submission


def _preparation_payload(submission, remote=None):
    remote = remote if isinstance(remote, dict) else {}
    stored = submission.preparation_metadata if isinstance(submission.preparation_metadata, dict) else {}
    metadata = {"mode": submission.source_mode or remote.get("mode")}
    for key in ("frame_count", "has_geo_txt", "manifest_schema", "source_hashes", "telemetry_summary"):
        if key in stored:
            metadata[key] = stored[key]
    return {
        "submission_id": str(submission.id),
        "task_id": str(submission.task_id) if submission.task_id else None,
        "project_id": str(submission.project_id) if submission.project_id else None,
        "job_id": submission.companion_job_id or remote.get("job_id"),
        "mode": submission.source_mode or remote.get("mode"),
        "status": submission.preparation_state or remote.get("status") or "unknown",
        # Companion responses can contain host-local paths and raw diagnostics.
        # Only the explicit path-free summary crosses into the browser.
        "metadata": metadata,
    }


def _safe_bundle_member(name):
    path = Path(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name


def _extract_preparation_bundle(bundle, destination):
    """Extract and validate a companion bundle into a request-owned temp dir."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(bundle) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
            if not members:
                raise serializers.ValidationError("The preparation bundle is empty.")
            if len(members) > PREPARATION_BUNDLE_MAX_MEMBERS:
                raise serializers.ValidationError("The preparation bundle contains too many files.")
            if any(not _safe_bundle_member(info.filename) for info in members):
                raise serializers.ValidationError("The preparation bundle contains an unsafe path.")
            uncompressed_bytes = sum(max(0, info.file_size) for info in members)
            if uncompressed_bytes > PREPARATION_BUNDLE_MAX_UNCOMPRESSED_BYTES:
                raise serializers.ValidationError("The preparation bundle exceeds the extraction limit.")
            for info in members:
                target = (destination / info.filename).resolve()
                try:
                    target.relative_to(destination)
                except ValueError:
                    raise serializers.ValidationError("The preparation bundle contains an unsafe path.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    except zipfile.BadZipFile as exc:
        raise serializers.ValidationError("The preparation bundle is not a valid ZIP file.") from exc
    return destination


def _prepared_files(extracted):
    extracted = Path(extracted)
    frames_root = extracted / "frames"
    frames = sorted(
        path
        for path in frames_root.iterdir()
        if path.is_file() and path.suffix.lower() in PREPARATION_IMAGE_SUFFIXES
    ) if frames_root.is_dir() else []
    if not frames:
        raise serializers.ValidationError("The preparation bundle contains no prepared frames.")
    names = [path.name for path in frames]
    if len(names) != len(set(names)):
        raise serializers.ValidationError("The preparation bundle contains duplicate frame names.")
    manifest_path = extracted / "manifest.json"
    manifest = _read_preparation_json(manifest_path, "frame manifest", required=True)
    if not isinstance(manifest, dict):
        raise serializers.ValidationError("The prepared manifest has an unsupported structure.")
    manifest_frames = manifest.get("frames")
    if not isinstance(manifest_frames, list):
        raise serializers.ValidationError("The prepared manifest contains no frame list.")
    if any(not isinstance(item, dict) for item in manifest_frames):
        raise serializers.ValidationError("The prepared manifest contains an invalid frame record.")
    manifest_names = [str(item.get("output_filename", "")) for item in manifest_frames]
    if sorted(manifest_names) != names:
        raise serializers.ValidationError("Prepared frame files do not match the manifest.")
    geo_txt = extracted / "geo.txt"
    if geo_txt.exists() and not geo_txt.is_file():
        raise serializers.ValidationError("The prepared geo.txt is not a regular file.")
    return frames, geo_txt if geo_txt.is_file() else None, manifest


def _evidence_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _evidence_integer(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if str(number) == str(value).strip() or isinstance(value, int) else None


def _evidence_text(value, limit=256):
    return value[:limit] if isinstance(value, str) else ""


def _evidence_strings(value, limit=100):
    if not isinstance(value, list):
        return []
    return [_evidence_text(item, 512) for item in value[:limit] if isinstance(item, str)]


def _evidence_sha256(value):
    value = value.lower() if isinstance(value, str) else ""
    return value if re.fullmatch(r"[0-9a-f]{64}", value) else None


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_preparation_json(path, label, required=False):
    path = Path(path)
    if not path.is_file():
        if required:
            raise serializers.ValidationError("The preparation bundle is missing {}.".format(label))
        return None
    if path.stat().st_size > PREPARATION_EVIDENCE_MAX_BYTES:
        raise serializers.ValidationError("{} exceeds the preparation metadata size limit.".format(label))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise serializers.ValidationError("{} is unreadable.".format(label)) from exc


def _evidence_dimensions(value):
    if not isinstance(value, dict):
        return None
    width = _evidence_integer(value.get("width"))
    height = _evidence_integer(value.get("height"))
    if width is None or height is None or width < 1 or height < 1:
        return None
    return {"width": width, "height": height}


def _preparation_review_documents(extracted, manifest, frame_files, mode, remote):
    """Build path-free, bounded review records from a validated companion bundle."""
    if mode not in {"local", "georeferenced"}:
        raise serializers.ValidationError({"mode": "The preparation mode is invalid."})
    if manifest.get("mode") and manifest["mode"] != mode:
        raise serializers.ValidationError("The prepared manifest mode does not match the intake.")
    if "georeferenced" in manifest and bool(manifest["georeferenced"]) != (mode == "georeferenced"):
        raise serializers.ValidationError("The prepared manifest georeferencing flag is inconsistent.")

    raw_frames = manifest.get("frames")
    frame_by_name = {str(item.get("output_filename", "")): item for item in raw_frames}
    prepared_manifest = Path(extracted) / "manifest.json"
    result = remote.get("result") if isinstance(remote, dict) else {}
    if not isinstance(result, dict):
        result = {}
    source_video_hash = _evidence_sha256(result.get("source_video_sha256"))
    frame_rows = []
    for frame_path in frame_files:
        source = frame_by_name.get(frame_path.name)
        if not isinstance(source, dict):
            raise serializers.ValidationError("A prepared frame is missing from its manifest.")
        expected_hash = _evidence_sha256(source.get("sha256"))
        actual_hash = _file_sha256(frame_path)
        if expected_hash and actual_hash != expected_hash:
            raise serializers.ValidationError("A prepared frame does not match its manifest hash.")
        dimensions = _evidence_dimensions(source.get("dimensions"))
        source_dimensions = _evidence_dimensions(source.get("source_dimensions"))
        transformations = source.get("transformations")
        rotation = transformations.get("rotation") if isinstance(transformations, dict) else None
        timestamp = _evidence_number(source.get("source_timestamp_seconds"))
        frame_rows.append({
            "filename": frame_path.name,
            "source_frame_index": _evidence_integer(source.get("source_frame_index")),
            "timestamp_seconds": timestamp,
            "dimensions": dimensions,
            "source_dimensions": source_dimensions,
            "sha256": expected_hash or actual_hash,
            "rotation": _evidence_text(str(rotation), 64) if rotation is not None else None,
            "quality_status": "not_measured",
            "metadata_status": "available" if dimensions and expected_hash and timestamp is not None else "partial",
            "telemetry": {"status": "not_used" if mode == "local" else "unknown"},
        })

    # Selection outputs are advisory evidence only. Keep R1's complete source
    # frame set, and only expose a diagnostic when the companion produced a
    # schema-valid, one-to-one report for the imported candidates.
    selection_path = Path(extracted) / "selection" / "advisory.json"
    try:
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        selection = None
    if isinstance(selection, dict) and selection.get("schema_version") == "astrakriti3d.selection-advisory.v1":
        diagnostic_rows = selection.get("rows")
        if isinstance(diagnostic_rows, list) and len(diagnostic_rows) == len(frame_rows):
            metric_keys = (
                "blur_score", "clipped_ratio", "feature_count", "useful_match_count",
                "match_ratio", "median_feature_displacement", "new_feature_ratio",
                "image_similarity",
            )
            for index, diagnostic in enumerate(diagnostic_rows):
                if not isinstance(diagnostic, dict) or diagnostic.get("frame_number") != index + 1:
                    continue
                quality = {}
                for key in metric_keys:
                    raw_value = diagnostic.get(key)
                    if key in {"feature_count", "useful_match_count"}:
                        parsed = _evidence_integer(raw_value)
                        if parsed is not None and parsed >= 0:
                            quality[key] = parsed
                    else:
                        parsed = _evidence_number(raw_value)
                        if parsed is not None:
                            quality[key] = parsed
                if quality:
                    frame_rows[index]["quality_status"] = "measured"
                    frame_rows[index]["quality_metrics"] = quality
                elif diagnostic.get("diagnostics_status") == "uncertain":
                    frame_rows[index]["quality_status"] = "uncertain"
                    frame_rows[index]["quality_warning"] = _evidence_text(diagnostic.get("warning"), 256) or "Image diagnostics could not be measured."
                frame_rows[index]["selection_recommendation"] = _evidence_text(diagnostic.get("decision"), 16) or None
                frame_rows[index]["selection_reason"] = _evidence_text(diagnostic.get("rejection_reason"), 128) or None
            coverage = selection.get("coverage")
            coverage_rows = coverage.get("rows") if isinstance(coverage, dict) else None
            if isinstance(coverage_rows, list):
                coverage_by_name = {
                    _evidence_text(row.get("output_filename"), 255): row
                    for row in coverage_rows if isinstance(row, dict)
                }
                for row in frame_rows:
                    recommended = coverage_by_name.get(row["filename"])
                    if recommended:
                        row["coverage_recommendation"] = _evidence_text(recommended.get("decision"), 16) or None
                        row["coverage_reason"] = _evidence_text(recommended.get("reason"), 128) or None
        frames_document_selection = {
            "status": _evidence_text(selection.get("status"), 24) or "unknown",
            "baseline": "R1",
            "policy": "advisory_only_all_source_frames_retained",
            "warnings": [
                _evidence_text(item, 512)
                for item in selection.get("warnings", [])[:16]
                if isinstance(item, str)
            ] if isinstance(selection.get("warnings"), list) else [],
        }
    else:
        frames_document_selection = {
            "status": "unavailable",
            "baseline": "R1",
            "policy": "advisory_only_all_source_frames_retained",
            "warnings": ["Experimental selector diagnostics were not present in the preparation bundle."],
        }

    if mode == "local":
        telemetry = {
            "schema_version": PREPARATION_EVIDENCE_SCHEMA,
            "status": "not_applicable",
            "coordinate_reference": "local / unreferenced",
            "altitude_units": "unknown",
            "summary": {
                "record_count": 0,
                "valid_record_count": 0,
                "invalid_record_count": 0,
                "parser_error_count": 0,
                "matched_frame_count": 0,
                "unmatched_frame_count": 0,
                "warnings": ["Telemetry was not used in local/unreferenced mode."],
                "errors": [],
                "unknowns": ["Absolute geographic position and vertical reference are unavailable."],
            },
            "records": [],
        }
    else:
        telemetry_root = Path(extracted) / "telemetry"
        report = _read_preparation_json(
            telemetry_root / "telemetry_report.json", "telemetry report", required=True
        )
        association_document = _read_preparation_json(
            telemetry_root / "association_manifest.json", "frame/telemetry associations", required=True
        )
        raw_records = _read_preparation_json(
            telemetry_root / "telemetry_ordered.json", "parsed telemetry records", required=True
        )
        if not isinstance(report, dict) or not isinstance(report.get("srt"), dict) or not isinstance(report.get("association"), dict):
            raise serializers.ValidationError("The telemetry report has an unsupported structure.")
        if not isinstance(association_document, dict) or not isinstance(association_document.get("rows"), list):
            raise serializers.ValidationError("The frame/telemetry association manifest has an unsupported structure.")
        if not isinstance(raw_records, list) or any(not isinstance(item, dict) for item in raw_records):
            raise serializers.ValidationError("The parsed telemetry records have an unsupported structure.")

        association_rows = association_document["rows"]
        if len(association_rows) != len(frame_rows):
            raise serializers.ValidationError("The telemetry associations do not match the prepared frame count.")
        frame_names = {row["filename"] for row in frame_rows}
        frame_rows_by_name = {row["filename"]: row for row in frame_rows}
        seen_frame_names = set()
        record_to_frames = {}
        matched_frames = 0
        unmatched_frames = 0
        for association in association_rows:
            if not isinstance(association, dict):
                raise serializers.ValidationError("The telemetry association manifest contains an invalid row.")
            filename = _evidence_text(association.get("frame_filename"), 255)
            state = association.get("association_status")
            if filename not in frame_names or filename in seen_frame_names or state not in {"matched", "unmatched"}:
                raise serializers.ValidationError("The telemetry association manifest contains an invalid frame reference.")
            seen_frame_names.add(filename)
            if state == "matched":
                record_id = _evidence_text(association.get("telemetry_record_id"), 128)
                latitude = _evidence_number(association.get("latitude"))
                longitude = _evidence_number(association.get("longitude"))
                if not record_id or latitude is None or longitude is None or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                    raise serializers.ValidationError("A matched telemetry association has invalid coordinates.")
                record_to_frames.setdefault(record_id, []).append(filename)
                matched_frames += 1
            else:
                unmatched_frames += 1
            frame_rows_by_name[filename]["telemetry"] = {
                "status": state,
                "record_id": _evidence_text(association.get("telemetry_record_id"), 128) or None,
                "timestamp_seconds": _evidence_number(association.get("matched_telemetry_timestamp_seconds")),
                "difference_seconds": _evidence_number(association.get("signed_time_difference_seconds")),
                "latitude": _evidence_number(association.get("latitude")),
                "longitude": _evidence_number(association.get("longitude")),
                "altitude": _evidence_number(association.get("altitude")),
                "heading": _evidence_number(association.get("heading")),
            }
        if seen_frame_names != frame_names:
            raise serializers.ValidationError("The telemetry association manifest omits a prepared frame.")

        srt = report["srt"]
        association_summary = report["association"]
        reported_record_count = _evidence_integer(srt.get("record_count"))
        if reported_record_count is not None and reported_record_count != len(raw_records):
            raise serializers.ValidationError("The telemetry report count does not match its parsed records.")
        parser_errors = _evidence_strings(srt.get("errors"), 1000)
        invalid_records = _evidence_integer(srt.get("invalid_record_count")) or 0
        if invalid_records or parser_errors or unmatched_frames:
            raise serializers.ValidationError("Georeferenced preparation contains invalid or unmatched telemetry.")
        reported_frames = _evidence_integer(association_summary.get("frame_count"))
        reported_matched = _evidence_integer(association_summary.get("matched_count"))
        reported_unmatched = _evidence_integer(association_summary.get("unmatched_count"))
        if reported_frames not in (None, len(frame_rows)) or reported_matched not in (None, matched_frames) or reported_unmatched not in (None, unmatched_frames):
            raise serializers.ValidationError("The telemetry report counts do not match its association manifest.")

        records = []
        for source in raw_records:
            record_id = _evidence_text(source.get("record_id"), 128)
            fields = source.get("fields") if isinstance(source.get("fields"), dict) else {}
            speed = None
            for key, value in fields.items():
                normalized = str(key).strip().lower().replace("-", "_")
                if normalized in {"speed", "speed_mps", "ground_speed", "groundspeed", "horizontal_speed"}:
                    speed = _evidence_number(value)
                    if speed is None:
                        speed = _evidence_text(value, 64) or None
                    break
            records.append({
                "record_id": record_id,
                "timestamp_seconds": _evidence_number(source.get("cue_start_seconds")),
                "wall_clock_time": _evidence_text(source.get("wall_clock_time"), 64) or None,
                "latitude": _evidence_number(source.get("latitude")),
                "longitude": _evidence_number(source.get("longitude")),
                "altitude": _evidence_number(source.get("altitude")),
                "altitude_units": "unknown",
                "heading": _evidence_number(source.get("heading")),
                "speed": speed,
                "speed_units": "unknown" if speed is not None else None,
                "valid": source.get("valid") if isinstance(source.get("valid"), bool) else None,
                "diagnostics": _evidence_strings(source.get("diagnostics"), 50),
                "associated_frames": record_to_frames.get(record_id, []),
            })

        source_video = report.get("source_video") if isinstance(report.get("source_video"), dict) else {}
        source_hashes = {
            "video": _evidence_sha256(source_video.get("sha256")) or source_video_hash,
            "telemetry": _evidence_sha256(srt.get("sha256")),
            "frame_manifest": _file_sha256(prepared_manifest),
            "association_manifest": _file_sha256(telemetry_root / "association_manifest.json"),
        }
        raw_time_range = srt.get("timestamp_range_seconds")
        timestamp_range = None
        if isinstance(raw_time_range, list) and len(raw_time_range) == 2:
            start_time, end_time = (_evidence_number(value) for value in raw_time_range)
            if start_time is not None and end_time is not None:
                timestamp_range = [start_time, end_time]
        duplicate_ids = srt.get("duplicates") if isinstance(srt.get("duplicates"), list) else []
        non_monotonic_ids = srt.get("non_monotonic") if isinstance(srt.get("non_monotonic"), list) else []
        gap_values = srt.get("gaps_seconds") if isinstance(srt.get("gaps_seconds"), list) else []
        telemetry = {
            "schema_version": _evidence_text(report.get("schema_version"), 96) or PREPARATION_EVIDENCE_SCHEMA,
            "status": "available",
            "coordinate_reference": "EPSG:4326",
            "altitude_units": _evidence_text(srt.get("altitude_units"), 64) or "unknown",
            "source_hashes": source_hashes,
            "summary": {
                "record_count": reported_record_count if reported_record_count is not None else len(records),
                "valid_record_count": _evidence_integer(srt.get("valid_record_count")),
                "invalid_record_count": invalid_records,
                "parser_error_count": len(parser_errors),
                "ignored_block_count": len(srt.get("errors")) if isinstance(srt.get("errors"), list) else 0,
                "duplicate_timestamp_count": len(duplicate_ids),
                "non_monotonic_timestamp_count": len(non_monotonic_ids),
                "gap_count": len(gap_values),
                "matched_frame_count": matched_frames,
                "unmatched_frame_count": unmatched_frames,
                "time_offset_seconds": _evidence_number(srt.get("time_offset_seconds")),
                "association_tolerance_seconds": _evidence_number(association_summary.get("configured_tolerance_seconds")),
                "timestamp_range_seconds": timestamp_range,
                "warnings": _evidence_strings(report.get("warnings"), 1000),
                "errors": parser_errors,
                "assumptions": _evidence_strings(report.get("assumptions"), 100),
                "unknowns": _evidence_strings(report.get("unknowns"), 100),
            },
            "records": records,
        }

    manifest_sampling = manifest.get("sampling") if isinstance(manifest.get("sampling"), dict) else {}
    frames_document = {
        "schema_version": PREPARATION_EVIDENCE_SCHEMA,
        "mode": mode,
        "coordinate_reference": "EPSG:4326" if mode == "georeferenced" else "local / unreferenced",
        "frame_count": len(frame_rows),
        "source_hashes": {
            "video": source_video_hash or telemetry.get("source_hashes", {}).get("video"),
            "frame_manifest": _file_sha256(prepared_manifest),
            "telemetry": telemetry.get("source_hashes", {}).get("telemetry"),
        },
        "sampling": {
            "rule": _evidence_text(manifest_sampling.get("rule"), 256),
            "interval_seconds": _evidence_number(manifest_sampling.get("interval_seconds")),
            "extraction_mode": _evidence_text(manifest_sampling.get("extraction_mode"), 64) or None,
        },
        "selection": frames_document_selection,
        "frames": frame_rows,
    }
    return frames_document, telemetry


def _task_preparation_directory(task, create=False):
    task_root = Path(task.task_path()).resolve()
    directory = Path(task.data_path("astrakriti3d"))
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    resolved = directory.resolve()
    try:
        resolved.relative_to(task_root)
    except ValueError as exc:
        raise ValueError("Task preparation evidence escaped the Task data directory.") from exc
    return resolved


def _write_task_preparation_review(task, frames_document, telemetry_document):
    directory = _task_preparation_directory(task, create=True)
    for filename, document in (("frames.json", frames_document), ("telemetry.json", telemetry_document)):
        encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > PREPARATION_EVIDENCE_MAX_BYTES:
            raise serializers.ValidationError("Prepared review metadata exceeds the configured size limit.")
        handle = tempfile.NamedTemporaryFile(
            prefix=".{}-".format(filename), suffix=".tmp", dir=str(directory), delete=False
        )
        temporary = Path(handle.name)
        try:
            with handle:
                handle.write(encoded)
            os.replace(str(temporary), str(directory / filename))
        finally:
            temporary.unlink(missing_ok=True)


def _read_task_preparation_review(task, filename):
    directory = _task_preparation_directory(task)
    path = directory / filename
    if not path.is_file() or path.is_symlink():
        return None
    if path.stat().st_size > PREPARATION_EVIDENCE_MAX_BYTES:
        raise ValueError("Stored preparation review metadata exceeds the configured size limit.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Stored preparation review metadata has an invalid structure.")
    return value


def _review_page_parameters(request, default_limit):
    try:
        offset = int(request.query_params.get("offset", "0"))
        requested_limit = int(request.query_params.get("limit", str(default_limit)))
    except (TypeError, ValueError):
        raise serializers.ValidationError("Review pagination values must be integers.")
    if offset < 0:
        raise serializers.ValidationError({"offset": "Offset cannot be negative."})
    return offset, min(max(requested_limit, 1), 100), _evidence_text(request.query_params.get("q", ""), 128).strip().lower()


class TaskPreparationEvidenceView(TaskNestedView):
    """Read authenticated, task-scoped frame and telemetry review evidence."""

    def get(self, request, pk=None):
        task = self.get_and_check_task(request, pk)
        view = request.query_params.get("view", "frames")
        if view not in {"frames", "telemetry"}:
            raise serializers.ValidationError({"view": "Choose frames or telemetry."})
        default_limit = 48 if view == "frames" else 100
        offset, limit, query = _review_page_parameters(request, default_limit)
        filename = "frames.json" if view == "frames" else "telemetry.json"
        try:
            document = _read_task_preparation_review(task, filename)
        except (OSError, ValueError, TypeError):
            return Response(
                {
                    "status": "error",
                    "view": view,
                    "detail": "Stored preparation evidence could not be read. Existing WebODM task data was not changed.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if document is None:
            if view == "frames":
                frames = []
                for frame_name in sorted(task.scan_images()):
                    if not str(frame_name).lower().endswith(PREPARATION_IMAGE_SUFFIXES):
                        continue
                    try:
                        image_path = Path(task.get_image_path(frame_name))
                        preview_available = image_path.is_file()
                    except (OSError, ValueError):
                        preview_available = False
                    frames.append({
                        "filename": Path(frame_name).name,
                        "source_frame_index": None,
                        "timestamp_seconds": None,
                        "dimensions": None,
                        "source_dimensions": None,
                        "sha256": None,
                        "quality_status": "not_measured",
                        "metadata_status": "partial",
                        "telemetry": {"status": "unknown"},
                        "preview_available": preview_available,
                        **({
                            "thumbnail_url": "/api/projects/{}/tasks/{}/images/thumbnail/{}".format(
                                task.project_id, task.id, quote(Path(frame_name).name, safe="")
                            ),
                            "download_url": "/api/projects/{}/tasks/{}/images/download/{}".format(
                                task.project_id, task.id, quote(Path(frame_name).name, safe="")
                            ),
                        } if preview_available else {}),
                    })
                association_filter = request.query_params.get("association", "all")
                if association_filter not in {"all", "matched", "unmatched"}:
                    raise serializers.ValidationError({"association": "Choose all, matched, or unmatched."})
                filtered_frames = [
                    row for row in frames
                    if (association_filter == "all" and (not query or query in row["filename"].lower()))
                ]
                page = filtered_frames[offset:offset + limit]
                return Response(
                    {
                        "status": "partial" if frames else "unavailable",
                        "view": view,
                        "mode": "unknown",
                        "detail": "WebODM source images are available, but no Astrakriti preparation manifest was imported. Timestamps, GPS association, and quality scores are not available.",
                        "offset": offset,
                        "limit": limit,
                        "total": len(filtered_frames),
                        "items": page,
                    },
                    status=status.HTTP_200_OK,
                )

            legacy_records = []
            for media in task.media if isinstance(task.media, list) else []:
                if not isinstance(media, dict) or not isinstance(media.get("geolocation"), dict):
                    continue
                geolocation = media["geolocation"]
                normalized = {str(key).strip().lower(): value for key, value in geolocation.items()}
                latitude = _evidence_number(normalized.get("latitude", normalized.get("lat")))
                longitude = _evidence_number(normalized.get("longitude", normalized.get("lon", normalized.get("lng"))))
                altitude = _evidence_number(normalized.get("altitude", normalized.get("alt")))
                if latitude is not None and not -90 <= latitude <= 90:
                    latitude = None
                if longitude is not None and not -180 <= longitude <= 180:
                    longitude = None
                legacy_records.append({
                    "record_id": _evidence_text(Path(str(media.get("filename") or "media")).name, 255),
                    "timestamp_seconds": None,
                    "wall_clock_time": None,
                    "latitude": latitude,
                    "longitude": longitude,
                    "altitude": altitude,
                    "altitude_units": "unknown",
                    "heading": _evidence_number(normalized.get("heading")),
                    "speed": None,
                    "speed_units": None,
                    "valid": None,
                    "diagnostics": ["WebODM media geolocation only; parsed SRT and frame association evidence are unavailable."],
                    "associated_frames": [],
                })
            if query:
                legacy_records = [row for row in legacy_records if query in json.dumps(row, sort_keys=True).lower()]
            has_coordinates = any(row["latitude"] is not None and row["longitude"] is not None for row in legacy_records)
            return Response(
                {
                    "status": "partial" if legacy_records else "unavailable",
                    "view": view,
                    "mode": "unknown",
                    "coordinate_reference": "EPSG:4326" if has_coordinates else "unknown",
                    "altitude_units": "unknown",
                    "detail": "Only WebODM media geolocation is available. Parsed SRT records, timestamps, and frame associations were not imported for this Task." if legacy_records else "No imported Astrakriti telemetry manifest or WebODM media geolocation is available for this Task.",
                    "summary": {
                        "record_count": None,
                        "valid_record_count": None,
                        "invalid_record_count": None,
                        "parser_error_count": None,
                        "matched_frame_count": None,
                        "unmatched_frame_count": None,
                        "warnings": [],
                        "errors": [],
                        "unknowns": ["Parsed SRT record totals and frame associations were not imported."],
                    },
                    "offset": offset,
                    "limit": limit,
                    "total": len(legacy_records),
                    "items": legacy_records[offset:offset + limit],
                },
                status=status.HTTP_200_OK,
            )

        if view == "frames":
            rows = document.get("frames")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                return Response(
                    {"status": "error", "view": view, "detail": "Stored frame evidence has an invalid structure."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            association_filter = request.query_params.get("association", "all")
            if association_filter not in {"all", "matched", "unmatched"}:
                raise serializers.ValidationError({"association": "Choose all, matched, or unmatched."})
            filtered = []
            for row in rows:
                telemetry = row.get("telemetry") if isinstance(row.get("telemetry"), dict) else {}
                if association_filter != "all" and telemetry.get("status") != association_filter:
                    continue
                if query and query not in json.dumps(
                    {key: row.get(key) for key in ("filename", "source_frame_index", "timestamp_seconds", "telemetry")},
                    sort_keys=True,
                ).lower():
                    continue
                filtered.append(row)
            items = []
            for row in filtered[offset:offset + limit]:
                item = dict(row)
                frame_name = _evidence_text(item.get("filename"), 255)
                try:
                    image_path = Path(task.get_image_path(frame_name))
                    preview_available = image_path.is_file()
                except (OSError, ValueError):
                    preview_available = False
                item["preview_available"] = preview_available
                if preview_available:
                    encoded = quote(frame_name, safe="")
                    item["thumbnail_url"] = "/api/projects/{}/tasks/{}/images/thumbnail/{}".format(
                        task.project_id, task.id, encoded
                    )
                    item["download_url"] = "/api/projects/{}/tasks/{}/images/download/{}".format(
                        task.project_id, task.id, encoded
                    )
                items.append(item)
            status_value = "partial" if any(row.get("metadata_status") != "available" for row in filtered) else "available"
            return Response(
                {
                    "status": status_value,
                    "view": view,
                    "mode": document.get("mode"),
                    "coordinate_reference": document.get("coordinate_reference"),
                    "sampling": document.get("sampling", {}),
                    "selection": document.get("selection", {
                        "status": "unavailable",
                        "baseline": "R1",
                        "policy": "advisory_only_all_source_frames_retained",
                    }),
                    "source_hashes": document.get("source_hashes", {}),
                    "offset": offset,
                    "limit": limit,
                    "total": len(filtered),
                    "frame_count": document.get("frame_count", len(rows)),
                    "items": items,
                    "detail": "Experimental selector diagnostics are unavailable for one or more frames; all R1 source frames remain included." if items and any(row.get("quality_status") != "measured" for row in items) else "",
                },
                status=status.HTTP_200_OK,
            )

        rows = document.get("records")
        summary = document.get("summary")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows) or not isinstance(summary, dict):
            return Response(
                {"status": "error", "view": view, "detail": "Stored telemetry evidence has an invalid structure."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        association_filter = request.query_params.get("association", "all")
        if association_filter not in {"all", "associated", "unassociated"}:
            raise serializers.ValidationError({"association": "Choose all, associated, or unassociated."})
        filtered = []
        for row in rows:
            associated_frames = row.get("associated_frames") if isinstance(row.get("associated_frames"), list) else []
            if association_filter == "associated" and not associated_frames:
                continue
            if association_filter == "unassociated" and associated_frames:
                continue
            if query and query not in json.dumps(row, sort_keys=True).lower():
                continue
            filtered.append(row)
        return Response(
            {
                "status": document.get("status", "unknown"),
                "view": view,
                "mode": document.get("mode"),
                "coordinate_reference": document.get("coordinate_reference"),
                "altitude_units": document.get("altitude_units", "unknown"),
                "summary": summary,
                "source_hashes": document.get("source_hashes", {}),
                "offset": offset,
                "limit": limit,
                "total": len(filtered),
                "items": filtered[offset:offset + limit],
            },
            status=status.HTTP_200_OK,
        )


def _task_image_count(task):
    return sum(
        1
        for name in task.scan_images()
        if str(name).lower().endswith(PREPARATION_IMAGE_SUFFIXES)
    )


FRAME_SELECTION_SCHEMA = "astrakriti3d.frame-selection.v1"


def _safe_frame_name(value):
    return (
        isinstance(value, str)
        and value not in {"", ".", "..", "geo.txt"}
        and Path(value).name == value
        and "/" not in value
        and "\\" not in value
        and Path(value).suffix.lower() in PREPARATION_IMAGE_SUFFIXES
    )


def _task_frame_candidates(task):
    rows_by_name = {}
    try:
        document = _read_task_preparation_review(task, "frames.json")
    except (OSError, ValueError, TypeError):
        document = None
    if isinstance(document, dict) and isinstance(document.get("frames"), list):
        rows_by_name = {
            row.get("filename"): row
            for row in document["frames"]
            if isinstance(row, dict) and _safe_frame_name(row.get("filename"))
        }
    names = sorted(
        Path(name).name
        for name in task.scan_images()
        if _safe_frame_name(Path(name).name)
    )
    candidates = []
    for name in names:
        path = Path(task.get_image_path(name))
        if not path.is_file() or path.is_symlink():
            continue
        row = dict(rows_by_name.get(name) or {})
        row.update({"filename": name, "sha256": _file_sha256(path)})
        candidates.append(row)
    return candidates


def _candidate_set_hash(candidate_hashes):
    encoded = json.dumps(candidate_hashes, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _geo_source_for_task(task):
    directory = _task_preparation_directory(task, create=True)
    source_path = directory / "source_geo.txt"
    if source_path.is_file() and not source_path.is_symlink():
        data = source_path.read_bytes()
    else:
        geo_path = Path(task.get_image_path("geo.txt"))
        if not geo_path.is_file() or geo_path.is_symlink():
            return None
        data = geo_path.read_bytes()
        temporary = directory / ".source_geo.txt.tmp"
        temporary.write_bytes(data)
        os.replace(str(temporary), str(source_path))
    return data


def _validated_geo_lines(geo_bytes, candidate_names):
    try:
        lines = geo_bytes.decode("utf-8").splitlines()
    except (AttributeError, UnicodeDecodeError) as exc:
        raise SubmissionConflict(detail=_("The original geo.txt is unreadable.")) from exc
    if not lines or lines[0].strip() != "EPSG:4326":
        raise SubmissionConflict(detail=_("The original geo.txt does not declare EPSG:4326."))
    records = {}
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        if len(parts) != 3 or not _safe_frame_name(parts[0]) or parts[0] in records:
            raise SubmissionConflict(detail=_("The original geo.txt has invalid or duplicate image records."))
        longitude = _evidence_number(parts[1])
        latitude = _evidence_number(parts[2])
        if longitude is None or latitude is None or not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise SubmissionConflict(detail=_("The original geo.txt has invalid coordinates."))
        records[parts[0]] = line
    if set(records) != set(candidate_names):
        raise SubmissionConflict(detail=_("The original geo.txt does not match the candidate image set."))
    return [lines[0], *(records[name] for name in candidate_names)]


def _atomic_task_file(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
    finally:
        temporary.unlink(missing_ok=True)


def _apply_submission_frame_selection(task, submission):
    metadata = submission.preparation_metadata if isinstance(submission.preparation_metadata, dict) else {}
    selection = metadata.get("frame_selection")
    if not isinstance(selection, dict) or selection.get("schema_version") != FRAME_SELECTION_SCHEMA:
        return _task_image_count(task)

    candidates = selection.get("candidate_hashes")
    selected_names = selection.get("selected_filenames")
    if not isinstance(candidates, dict) or not isinstance(selected_names, list):
        raise SubmissionConflict(detail=_("The saved frame-selection record is invalid."))
    candidate_names = sorted(candidates)
    if (
        len(candidate_names) < 2
        or any(not _safe_frame_name(name) for name in candidate_names)
        or len(set(selected_names)) != len(selected_names)
        or len(selected_names) < 2
        or not set(selected_names).issubset(candidates)
        or selection.get("candidate_set_sha256") != _candidate_set_hash(candidates)
    ):
        raise SubmissionConflict(detail=_("The saved frame selection no longer matches its candidates."))

    evidence_dir = _task_preparation_directory(task, create=True)
    archive = evidence_dir / "excluded"
    if archive.is_symlink():
        raise SubmissionConflict(detail=_("The frame-evidence archive path is unsafe."))
    try:
        archive.resolve().relative_to(evidence_dir.resolve())
    except ValueError as exc:
        raise SubmissionConflict(detail=_("The frame-evidence archive path is unsafe.")) from exc
    archive.mkdir(parents=True, exist_ok=True)

    for name in candidate_names:
        if not re.fullmatch(r"[0-9a-f]{64}", str(candidates.get(name, ""))):
            raise SubmissionConflict(detail=_("The candidate image hash record is invalid."))
        root_path = Path(task.get_image_path(name))
        archived_path = archive / name
        if archived_path.exists() and (archived_path.is_symlink() or not archived_path.is_file()):
            raise SubmissionConflict(detail=_("An archived candidate path is unsafe."))
        expected_hash = candidates[name]
        root_exists = root_path.is_file() and not root_path.is_symlink()
        archive_exists = archived_path.is_file()
        if root_exists and _file_sha256(root_path) != expected_hash:
            raise SubmissionConflict(detail=_("A candidate image changed after frame review."))
        if archive_exists and _file_sha256(archived_path) != expected_hash:
            raise SubmissionConflict(detail=_("An archived candidate image failed its provenance check."))

        if name in selected_names:
            if not root_exists:
                if not archive_exists:
                    raise SubmissionConflict(detail=_("A selected source frame is missing."))
                temporary = archive / ("." + name + ".restore.tmp")
                try:
                    shutil.copy2(archived_path, temporary)
                    if _file_sha256(temporary) != expected_hash:
                        raise SubmissionConflict(detail=_("A selected source frame failed its restore hash check."))
                    os.replace(str(temporary), str(root_path))
                finally:
                    temporary.unlink(missing_ok=True)
            if archive_exists:
                archived_path.unlink()
        else:
            if root_exists:
                if not archive_exists:
                    temporary = archive / ("." + name + ".tmp")
                    try:
                        shutil.copy2(root_path, temporary)
                        if _file_sha256(temporary) != expected_hash:
                            raise SubmissionConflict(detail=_("An excluded frame failed its archive hash check."))
                        os.replace(str(temporary), str(archived_path))
                    finally:
                        temporary.unlink(missing_ok=True)
                root_path.unlink()
            elif not archive_exists:
                raise SubmissionConflict(detail=_("An excluded source frame is missing."))

    root_images = {
        Path(name).name
        for name in task.scan_images()
        if _safe_frame_name(Path(name).name)
    }
    if root_images != set(selected_names):
        raise SubmissionConflict(detail=_("The Task image set does not match the saved selection."))

    geo_bytes = _geo_source_for_task(task)
    if geo_bytes is not None:
        source_geo_hash = hashlib.sha256(geo_bytes).hexdigest()
        if selection.get("source_geo_sha256") != source_geo_hash:
            raise SubmissionConflict(detail=_("The authoritative source geo.txt changed after frame review."))
        original_lines = _validated_geo_lines(geo_bytes, candidate_names)
        original_by_name = {line.split()[0]: line for line in original_lines[1:]}
        selected_geo = "\n".join([original_lines[0], *(original_by_name[name] for name in candidate_names if name in set(selected_names))]) + "\n"
        _atomic_task_file(task.get_image_path("geo.txt"), selected_geo.encode("utf-8"))
    elif selection.get("source_geo_sha256") is not None:
        raise SubmissionConflict(detail=_("The reviewed geo.txt is no longer available."))

    return len(selected_names)


class IntakeReservationView(TaskNestedView):
    """Reserve one native Project/partial Task for a retry-safe intake."""

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = IntakeReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fingerprint = _intake_request_fingerprint(data)
        key = data["idempotency_key"]

        try:
            with transaction.atomic():
                try:
                    # Lock only the submission row. Project and Task are
                    # nullable during reservation, so select_related would
                    # produce outer joins that PostgreSQL refuses to lock.
                    submission = AstrakritiSubmission.objects.select_for_update().get(
                        idempotency_key=key
                    )
                except AstrakritiSubmission.DoesNotExist:
                    project = _intake_project(request, data)
                    task = Task.objects.create(
                        project=project,
                        name=data["task_name"].strip(),
                        partial=True,
                    )
                    submission = AstrakritiSubmission.objects.create(
                        idempotency_key=key,
                        request_fingerprint=fingerprint,
                        owner=request.user,
                        project=project,
                        task=task,
                        task_name=data["task_name"].strip(),
                        state="reserved",
                    )
                    return Response(
                        _intake_payload(submission, reused=False),
                        status=status.HTTP_201_CREATED,
                    )

                if submission.owner_id != request.user.id:
                    raise exceptions.NotFound()
                if submission.request_fingerprint != fingerprint:
                    raise SubmissionConflict()
                if submission.task is None or submission.project is None:
                    raise SubmissionConflict(
                        detail=_(
                            "The previous intake no longer has a native Project/Task. "
                            "Start a new reconstruction with a new submission identity."
                        )
                    )
                check_project_perms(
                    request, submission.project, perms=("change_project",)
                )
                return Response(
                    _intake_payload(submission, reused=True),
                    status=status.HTTP_200_OK,
                )
        except IntegrityError:
            # A concurrent request won the unique-key race. Re-read it and let
            # the normal fingerprint/owner checks produce the safe response.
            try:
                submission = AstrakritiSubmission.objects.select_related(
                    "project", "task"
                ).get(idempotency_key=key)
            except (AstrakritiSubmission.DoesNotExist, DjangoValidationError, ValueError):
                raise SubmissionConflict()
            if submission.owner_id != request.user.id:
                raise exceptions.NotFound()
            if submission.request_fingerprint != fingerprint:
                raise SubmissionConflict()
            if submission.task is None or submission.project is None:
                raise SubmissionConflict()
            check_project_perms(request, submission.project, perms=("change_project",))
            return Response(_intake_payload(submission, reused=True), status=status.HTTP_200_OK)


class IntakeFrameSelectionView(TaskNestedView):
    """Persist an owner-authorized frame set before the native Task is committed."""

    permission_classes = (IsAuthenticated,)

    @staticmethod
    def _payload(task, submission, offset=0, limit=48):
        candidates = _task_frame_candidates(task)
        metadata = submission.preparation_metadata if isinstance(submission.preparation_metadata, dict) else {}
        saved = metadata.get("frame_selection") if isinstance(metadata.get("frame_selection"), dict) else {}
        try:
            frame_document = _read_task_preparation_review(task, "frames.json")
        except (OSError, ValueError, TypeError):
            frame_document = None
        names = [row["filename"] for row in candidates]
        selected = saved.get("selected_filenames") if isinstance(saved.get("selected_filenames"), list) else names
        selected_set = set(selected)
        items = []
        for row in candidates[offset:offset + limit]:
            item = dict(row)
            filename = item["filename"]
            encoded = quote(filename, safe="")
            item["preview_available"] = Path(task.get_image_path(filename)).is_file()
            if item["preview_available"]:
                item["thumbnail_url"] = "/api/projects/{}/tasks/{}/images/thumbnail/{}".format(
                    task.project_id, task.id, encoded
                )
                item["download_url"] = "/api/projects/{}/tasks/{}/images/download/{}".format(
                    task.project_id, task.id, encoded
                )
            item["selected"] = filename in selected_set
            items.append(item)
        r2_names = [row["filename"] for row in candidates if row.get("selection_recommendation") == "keep"]
        coverage_names = [row["filename"] for row in candidates if row.get("coverage_recommendation") == "keep"]
        return {
            "status": "available" if candidates else "waiting_for_inputs",
            "submission_id": str(submission.id),
            "task_id": str(task.id),
            "project_id": str(task.project_id),
            "task_name": task.name,
            "mode": submission.source_mode or "stills",
            "partial": bool(task.partial),
            "total": len(candidates),
            "offset": offset,
            "limit": limit,
            "strategy": saved.get("strategy") or "r1_all",
            "candidate_filenames": names,
            "selected_filenames": [name for name in names if name in selected_set],
            "r2_filenames": r2_names,
            "coverage_filenames": coverage_names,
            "selection_diagnostics": (
                frame_document.get("selection", {})
                if submission.preparation_state == "imported" and isinstance(frame_document, dict)
                else {"status": "unavailable"}
            ),
            "items": items,
        }

    def get(self, request, submission_id=None):
        submission = _submission_for_write(request, submission_id)
        try:
            offset, limit, _query = _review_page_parameters(request, 48)
        except serializers.ValidationError:
            raise
        return Response(self._payload(submission.task, submission, offset, limit))

    def post(self, request, submission_id=None):
        submission = _submission_for_write(request, submission_id)
        serializer = IntakeFrameSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested = serializer.validated_data["selected_filenames"]
        strategy = serializer.validated_data["strategy"]
        if len(set(requested)) != len(requested) or any(not _safe_frame_name(name) for name in requested):
            raise serializers.ValidationError({"selected_filenames": "Frame names must be unique safe image filenames."})

        with transaction.atomic():
            task = Task.objects.select_for_update().get(pk=submission.task_id, project=submission.project)
            submission = AstrakritiSubmission.objects.select_for_update().get(pk=submission.pk)
            if not task.partial:
                raise SubmissionConflict(detail=_("Frame selection is locked after processing starts."))
            rows = _task_frame_candidates(task)
            if len(rows) > PREPARATION_BUNDLE_MAX_MEMBERS:
                raise serializers.ValidationError({"selected_filenames": "This Task has too many candidate frames to select safely."})
            candidate_names = [row["filename"] for row in rows]
            if len(candidate_names) < 2 or not set(requested).issubset(candidate_names):
                raise serializers.ValidationError({"selected_filenames": "Choose at least two available candidate frames."})
            if len(requested) < 2:
                raise serializers.ValidationError({"selected_filenames": "At least two frames must be selected."})
            if strategy == "r1_all" and set(requested) != set(candidate_names):
                raise serializers.ValidationError({"selected_filenames": "R1 retains every candidate frame."})
            if strategy == "r2_advisory":
                suggested = {row["filename"] for row in rows if row.get("selection_recommendation") == "keep"}
                if not suggested or set(requested) != suggested:
                    raise serializers.ValidationError({"selected_filenames": "The submitted set does not match the recorded R2 recommendation."})
            if strategy == "coverage_advisory":
                suggested = {row["filename"] for row in rows if row.get("coverage_recommendation") == "keep"}
                if not suggested or set(requested) != suggested:
                    raise serializers.ValidationError({"selected_filenames": "The submitted set does not match the recorded coverage recommendation."})

            candidate_hashes = {row["filename"]: row["sha256"] for row in rows}
            source_geo = _geo_source_for_task(task)
            if submission.source_mode == "georeferenced":
                if source_geo is None:
                    raise SubmissionConflict(detail=_("The reviewed georeferenced Task has no source geo.txt."))
                _validated_geo_lines(source_geo, candidate_names)
            elif source_geo is not None:
                raise SubmissionConflict(detail=_("Local/unreferenced frame selection must not contain geo.txt."))

            value = {
                "schema_version": FRAME_SELECTION_SCHEMA,
                "strategy": strategy,
                "selected_filenames": [name for name in candidate_names if name in set(requested)],
                "candidate_hashes": candidate_hashes,
                "candidate_set_sha256": _candidate_set_hash(candidate_hashes),
                "source_geo_sha256": hashlib.sha256(source_geo).hexdigest() if source_geo is not None else None,
                "applied": False,
            }
            metadata = submission.preparation_metadata if isinstance(submission.preparation_metadata, dict) else {}
            previous = metadata.get("frame_selection") if isinstance(metadata.get("frame_selection"), dict) else {}
            reused = (
                previous.get("schema_version") == FRAME_SELECTION_SCHEMA
                and previous.get("strategy") == value["strategy"]
                and previous.get("selected_filenames") == value["selected_filenames"]
                and previous.get("candidate_set_sha256") == value["candidate_set_sha256"]
                and previous.get("source_geo_sha256") == value["source_geo_sha256"]
            )
            metadata = dict(metadata)
            if not reused:
                metadata["frame_selection"] = value
                submission.preparation_metadata = metadata
                submission.save(update_fields=("preparation_metadata", "updated_at"))
            else:
                value = previous

        return Response({
            "status": "saved",
            "reused": reused,
            "strategy": value["strategy"],
            "candidate_count": len(candidate_names),
            "selected_count": len(value["selected_filenames"]),
            "selected_filenames": value["selected_filenames"],
        }, status=status.HTTP_200_OK)


class IntakeCommitView(TaskNestedView):
    """Commit a reserved Task once, even if the browser retries the request."""

    permission_classes = (IsAuthenticated,)

    def post(self, request, submission_id=None):
        submission = _submission_for_write(request, submission_id)

        with transaction.atomic():
            task = Task.objects.select_for_update().get(
                pk=submission.task_id, project=submission.project
            )
            submission = AstrakritiSubmission.objects.select_for_update().get(pk=submission.pk)
            if not task.partial:
                submission.state = "committed"
                submission.save(update_fields=("state", "updated_at"))
                return Response(
                    {
                        "success": True,
                        "reused": True,
                        "submission_id": str(submission.id),
                        "project_id": str(task.project_id),
                        "task_id": str(task.id),
                    },
                    status=status.HTTP_200_OK,
                )

            task.images_count = _apply_submission_frame_selection(task, submission)
            if task.images_count < 1:
                raise serializers.ValidationError(
                    {"images": _("You need to upload at least 1 file before commit")}
                )
            task.update_size()
            task.partial = False
            task.save()
            submission.state = "committed"
            metadata = submission.preparation_metadata if isinstance(submission.preparation_metadata, dict) else {}
            selection = metadata.get("frame_selection") if isinstance(metadata.get("frame_selection"), dict) else None
            if selection is not None:
                selection = dict(selection)
                selection["applied"] = True
                selection["selected_count"] = task.images_count
                selection["selected_sha256"] = _candidate_set_hash({
                    name: selection["candidate_hashes"][name]
                    for name in selection["selected_filenames"]
                })
                metadata = dict(metadata)
                metadata["frame_selection"] = selection
                submission.preparation_metadata = metadata
                submission.save(update_fields=("state", "preparation_metadata", "updated_at"))
            else:
                submission.save(update_fields=("state", "updated_at"))
            transaction.on_commit(
                lambda task_id=task.id: worker_tasks.process_task.delay(task_id)
            )

        return Response(
            {
                "success": True,
                "reused": False,
                "submission_id": str(submission.id),
                "project_id": str(task.project_id),
                "task_id": str(task.id),
            },
            status=status.HTTP_200_OK,
        )


class IntakePreparationView(TaskNestedView):
    """Start or observe protected Astrakriti video/SRT preparation."""

    permission_classes = (IsAuthenticated,)

    def post(self, request, submission_id=None):
        submission = _submission_for_write(request, submission_id)
        if not submission.task.partial:
            return Response(_preparation_payload(submission), status=status.HTTP_200_OK)

        mode = str(request.data.get("mode") or "local").strip().lower()
        if mode not in {"local", "georeferenced"}:
            raise serializers.ValidationError({"mode": "mode must be local or georeferenced"})
        video = request.FILES.get("video")
        srt = request.FILES.get("srt")
        if video is None:
            raise serializers.ValidationError({"video": "A source video is required."})
        if mode == "georeferenced" and srt is None:
            raise serializers.ValidationError(
                {"srt": "Georeferenced preparation requires a telemetry SRT."}
            )

        client = AstrakritiCompanionClient()
        if not client.configured:
            raise CompanionUnavailable(
                detail=_("Video/SRT preparation is unavailable because the protected companion is not configured.")
            )
        if submission.companion_job_id:
            if submission.source_mode != mode:
                raise SubmissionConflict()
            return Response(_preparation_payload(submission), status=status.HTTP_202_ACCEPTED)

        staged_paths = []
        try:
            staged_video = _stage_companion_upload(video)
            staged_paths.append(staged_video)
            staged_srt = None
            if srt is not None:
                staged_srt = _stage_companion_upload(srt)
                staged_paths.append(staged_srt)
            with staged_video.open("rb") as video_handle:
                if staged_srt is not None:
                    with staged_srt.open("rb") as srt_handle:
                        remote = client.start_preparation(
                            submission.id,
                            mode,
                            video_handle,
                            srt=srt_handle,
                        )
                else:
                    remote = client.start_preparation(
                        submission.id,
                        mode,
                        video_handle,
                    )
        except (CompanionError, CompanionNotConfigured) as exc:
            raise CompanionUnavailable(detail=str(exc))
        finally:
            for staged_path in staged_paths:
                staged_path.unlink(missing_ok=True)
        job_id = str(remote.get("job_id") or submission.id)
        submission.companion_job_id = job_id
        submission.source_mode = mode
        submission.preparation_state = str(remote.get("status") or "queued")
        submission.preparation_metadata = remote
        submission.save(
            update_fields=(
                "companion_job_id",
                "source_mode",
                "preparation_state",
                "preparation_metadata",
                "updated_at",
            )
        )
        return Response(_preparation_payload(submission, remote), status=status.HTTP_202_ACCEPTED)

    def get(self, request, submission_id=None):
        submission = _submission_for_write(request, submission_id)
        if not submission.companion_job_id:
            return Response(_preparation_payload(submission), status=status.HTTP_200_OK)
        client = AstrakritiCompanionClient()
        if not client.configured:
            raise CompanionUnavailable(
                detail=_("Video/SRT preparation is unavailable because the protected companion is not configured.")
            )
        try:
            remote = client.preparation_status(submission.companion_job_id)
        except (CompanionError, CompanionNotConfigured) as exc:
            raise CompanionUnavailable(detail=str(exc))
        submission.preparation_state = str(remote.get("status") or "unknown")
        submission.preparation_metadata = remote
        submission.save(update_fields=("preparation_state", "preparation_metadata", "updated_at"))
        return Response(_preparation_payload(submission, remote), status=status.HTTP_200_OK)


class IntakePreparationImportView(TaskNestedView):
    """Import a completed companion bundle into the reserved native Task."""

    permission_classes = (IsAuthenticated,)

    def post(self, request, submission_id=None):
        submission = _submission_for_write(request, submission_id)
        if not submission.companion_job_id:
            raise SubmissionConflict(detail=_("No companion preparation is attached to this intake."))
        if submission.preparation_state == "imported":
            return Response(
                _preparation_payload(submission)
                | {"imported": True, "reused": True},
                status=status.HTTP_200_OK,
            )
        client = AstrakritiCompanionClient()
        if not client.configured:
            raise CompanionUnavailable(
                detail=_("Video/SRT preparation is unavailable because the protected companion is not configured.")
            )
        try:
            remote = client.preparation_status(submission.companion_job_id)
        except (CompanionError, CompanionNotConfigured) as exc:
            raise CompanionUnavailable(detail=str(exc))
        if remote.get("status") != "completed":
            return Response(
                _preparation_payload(submission, remote),
                status=status.HTTP_409_CONFLICT,
            )

        media_tmp = Path(settings.MEDIA_TMP)
        media_tmp.mkdir(parents=True, exist_ok=True)
        temporary_root = Path(tempfile.mkdtemp(prefix="astrakriti-preparation-", dir=str(media_tmp)))
        try:
            bundle = client.download_bundle(
                submission.companion_job_id, temporary_root / "prepared-input.zip"
            )
            extracted = _extract_preparation_bundle(bundle, temporary_root / "extracted")
            frames, geo_txt, manifest = _prepared_files(extracted)
            mode = submission.source_mode or remote.get("mode")
            if mode == "georeferenced" and geo_txt is None:
                raise serializers.ValidationError("Georeferenced preparation has no geo.txt input.")
            if mode == "local" and geo_txt is not None:
                raise serializers.ValidationError("Local preparation must not include geo.txt.")
            frames_document, telemetry_document = _preparation_review_documents(
                extracted, manifest, frames, mode, remote
            )
            task = Task.objects.get(pk=submission.task_id, project=submission.project)
            task_root = Path(task.task_path())
            task_root.mkdir(parents=True, exist_ok=True)
            if geo_txt is not None:
                evidence_dir = _task_preparation_directory(task, create=True)
                source_geo = evidence_dir / "source_geo.txt"
                if source_geo.is_symlink():
                    raise SubmissionConflict(detail=_("The stored source geo.txt path is unsafe."))
                if source_geo.is_file():
                    if _file_sha256(source_geo) != _file_sha256(geo_txt):
                        raise SubmissionConflict(detail=_("The imported source geo.txt changed on retry."))
                else:
                    shutil.copyfile(geo_txt, source_geo)
            for frame in frames:
                destination = Path(task.get_image_path(frame.name))
                shutil.copyfile(frame, destination)
            if geo_txt is not None:
                shutil.copyfile(geo_txt, Path(task.get_image_path("geo.txt")))
            _write_task_preparation_review(task, frames_document, telemetry_document)
            task.images_count = len(frames)
            task.save()
            submission.preparation_state = "imported"
            submission.preparation_metadata = {
                "mode": mode,
                "frame_count": len(frames),
                "has_geo_txt": geo_txt is not None,
                "manifest_schema": manifest.get("schema_version") if isinstance(manifest, dict) else None,
                "source_hashes": frames_document["source_hashes"],
                "telemetry_summary": telemetry_document["summary"],
            }
            submission.save(update_fields=("preparation_state", "preparation_metadata", "updated_at"))
        except (CompanionError, CompanionNotConfigured) as exc:
            raise CompanionUnavailable(detail=str(exc))
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)

        return Response(
            _preparation_payload(submission)
            | {"imported": True, "reused": False, "frame_count": task.images_count},
            status=status.HTTP_200_OK,
        )


class AstrakritiHealthView(TaskNestedView):
    def get(self, request):
        if not request.user.is_authenticated:
            raise exceptions.NotAuthenticated()
        return Response(_health_payload(request.user), status=status.HTTP_200_OK)


class MissionMetadataView(APIView):
    """Read/update Astrakriti-owned context for an authorized WebODM Project."""

    permission_classes = (IsAuthenticated,)

    def _project(self, request, pk, permission):
        try:
            project = Project.objects.get(pk=pk, deleting=False)
        except (Project.DoesNotExist, DjangoValidationError, ValueError):
            raise exceptions.NotFound()
        check_project_perms(request, project, perms=(permission,))
        return project

    @staticmethod
    def _payload(metadata, recorded=True):
        return {
            "project_id": str(metadata.project_id),
            "location": metadata.location,
            "capture_context": metadata.capture_context,
            "provenance": metadata.provenance,
            "schema_revision": metadata.schema_revision,
            "recorded": recorded,
            "updated_at": metadata.updated_at if recorded else None,
        }

    def get(self, request, pk=None):
        project = self._project(request, pk, "view_project")
        try:
            metadata = project.astrakriti_mission_metadata
        except AstrakritiMissionMetadata.DoesNotExist:
            metadata = AstrakritiMissionMetadata(project=project)
            return Response(self._payload(metadata, recorded=False))
        return Response(self._payload(metadata))

    def patch(self, request, pk=None):
        project = self._project(request, pk, "change_project")
        serializer = MissionMetadataSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        metadata, _ = AstrakritiMissionMetadata.objects.get_or_create(project=project)
        for field, value in serializer.validated_data.items():
            setattr(metadata, field, value)
        if serializer.validated_data:
            metadata.save(update_fields=tuple(serializer.validated_data) + ("updated_at",))
        return Response(self._payload(metadata))


class TaskMeasurementsView(TaskNestedView):
    def get(self, request, pk=None):
        task = self.get_and_check_task(request, pk)
        measurements = AstrakritiMeasurement.objects.filter(task=task).select_related("author")
        return Response(
            [_measurement_payload(measurement, task) for measurement in measurements],
            status=status.HTTP_200_OK,
        )

    def post(self, request, pk=None):
        task = self.get_and_check_task(request, pk)
        _require_write_access(request, task)
        serializer = MeasurementPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = _validate_payload(serializer.validated_data, task)
        measurement = AstrakritiMeasurement.objects.create(
            task=task,
            project=task.project,
            author=request.user,
            source_artifact_revision=artifact_revision(task),
            **payload,
        )
        return Response(
            _measurement_payload(measurement, task),
            status=status.HTTP_201_CREATED,
        )


class MeasurementDetailView(TaskNestedView):
    def _get_measurement(self, request, pk, measurement_id, for_update=False):
        task = self.get_and_check_task(request, pk)
        try:
            measurements = AstrakritiMeasurement.objects
            if for_update:
                measurements = measurements.select_for_update()
            measurement = measurements.get(
                id=measurement_id, task=task
            )
        except (AstrakritiMeasurement.DoesNotExist, DjangoValidationError, ValueError):
            raise exceptions.NotFound()
        return task, measurement

    def patch(self, request, pk=None, measurement_id=None):
        with transaction.atomic():
            task, measurement = self._get_measurement(
                request, pk, measurement_id, for_update=True
            )
            _require_write_access(request, task)
            serializer = MeasurementPayloadSerializer(data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            expected_updated_at = serializer.validated_data.get("expected_updated_at")
            if expected_updated_at is not None and measurement.updated_at != expected_updated_at:
                raise MeasurementConflict()
            payload = _validate_payload(serializer.validated_data, task, existing=measurement)
            for key, value in payload.items():
                setattr(measurement, key, value)
            measurement.source_artifact_revision = artifact_revision(task)
            measurement.full_clean()
            measurement.save()
            return Response(_measurement_payload(measurement, task), status=status.HTTP_200_OK)

    def delete(self, request, pk=None, measurement_id=None):
        task, measurement = self._get_measurement(request, pk, measurement_id)
        _require_write_access(request, task)
        measurement.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeasurementExportView(TaskNestedView):
    content_negotiation_class = MeasurementExportNegotiation

    def get(self, request, pk=None):
        task = self.get_and_check_task(request, pk)
        measurements = list(
            AstrakritiMeasurement.objects.filter(task=task).order_by("created_at")
        )
        if request.query_params.get("format") == "geojson" and any(
            measurement.crs not in ("", "EPSG:4326", "4326")
            for measurement in measurements
        ):
            raise exceptions.ValidationError(
                "GeoJSON export requires geographic EPSG:4326 coordinates"
            )

        if request.query_params.get("format") == "geojson":
            body = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": str(measurement.id),
                        "geometry": measurement.geometry,
                        "properties": {
                            "name": measurement.name,
                            "measurement_type": measurement.measurement_type,
                            "result": measurement.result,
                            "units": measurement.units,
                            "crs": measurement.crs or "EPSG:4326",
                            "method": measurement.method,
                            "task_id": str(task.id),
                            "project_id": str(task.project_id),
                            "source_artifact_revision": measurement.source_artifact_revision,
                        },
                    }
                    for measurement in measurements
                ],
            }
            content_type = "application/geo+json"
            filename = "astrakriti-measurements.geojson"
        else:
            body = {
                "schema": "astrakriti.measurements.v1",
                "task_id": str(task.id),
                "project_id": str(task.project_id),
                "artifact_revision": artifact_revision(task),
                "measurements": [
                    _measurement_payload(measurement, task) for measurement in measurements
                ],
            }
            content_type = "application/json"
            filename = "astrakriti-measurements.json"

        response = HttpResponse(
            json.dumps(body, default=str, indent=2), content_type=content_type
        )
        response["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
        return response

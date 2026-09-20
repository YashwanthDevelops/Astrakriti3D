import hashlib
import json
import os
import shutil
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from guardian.shortcuts import get_objects_for_user
from rest_framework.exceptions import NotFound

from app.api.common import check_project_perms
from app.geoutils import get_srs_name_units_from_epsg_or_wkt
from app.models import AstrakritiLegacyLink, AstrakritiMissionMetadata, Project, Task
from app.views.utils import get_permissions
from nodeodm import status_codes
from nodeodm.models import ProcessingNode

from .companion import AstrakritiCompanionClient


PAGE_LABELS = {
    "overview": "OVERVIEW",
    "missions": "MISSIONS",
    "mission": "MISSION OVERVIEW",
    "runs": "MISSION RUNS",
    "reconstructions": "RECONSTRUCTIONS",
    "artifacts": "ARTIFACTS",
    "reports": "REPORTS / EXPORTS",
    "processing": "PROCESSING / RECOVERY",
    "system": "SYSTEM HEALTH",
    "settings": "SETTINGS",
    "new-reconstruction": "NEW RECONSTRUCTION",
    "run": "RUN OVERVIEW",
    "frames": "FRAME REVIEW",
    "telemetry": "TELEMETRY REVIEW",
    "map": "MAP WORKSPACE",
    "model": "3D MODEL WORKSPACE",
    "measurements": "MEASUREMENTS",
    "validation": "VALIDATION / EVIDENCE",
    "files": "FILES",
}

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")

RUN_PAGES = (
    ("overview", "Overview"),
    ("frames", "Frames"),
    ("telemetry", "Telemetry"),
    ("map", "Map"),
    ("model", "3D Model"),
    ("measurements", "Measurements"),
    ("validation", "Validation"),
    ("reports", "Reports"),
    ("files", "Files"),
)


def _json(value):
    """Serialize server data safely for an application/json script element."""
    return (
        json.dumps(value, cls=DjangoJSONEncoder, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _task_state(task):
    return {
        None: "unknown",
        status_codes.QUEUED: "queued",
        status_codes.RUNNING: "processing",
        status_codes.FAILED: "failed",
        status_codes.COMPLETED: "completed",
        status_codes.CANCELED: "cancelled",
    }.get(task.status, "unknown")


def artifact_revision(task):
    """Return a cheap, deterministic revision for the task's current outputs."""
    entries = []
    for asset in sorted(set(task.available_assets or [])):
        try:
            path = task.get_asset_download_path(asset)
            stat = os.stat(path)
            entries.append((asset, stat.st_size, stat.st_mtime_ns))
        except (OSError, ValueError):
            entries.append((asset, None, None))
    payload = {
        "task": str(task.id),
        "status": task.status,
        "assets": entries,
        "srs": task.epsg or task.wkt or "",
    }
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _asset_payload(task, asset):
    try:
        path = task.get_asset_download_path(asset)
        exists = os.path.isfile(path)
        size = os.path.getsize(path) if exists else None
    except (OSError, ValueError):
        exists = False
        size = None

    return {
        "name": asset,
        "available": exists,
        "size": size,
        "download_url": "/api/projects/{}/tasks/{}/download/{}".format(
            task.project_id, task.id, quote(asset, safe="")
        ),
    }


def _task_frame_payload(task, limit=48):
    frames = []
    for filename in sorted(task.scan_images()):
        if not filename.lower().endswith(IMAGE_SUFFIXES):
            continue
        try:
            if not os.path.isfile(task.get_image_path(filename)):
                continue
        except (OSError, ValueError):
            continue
        encoded = quote(filename, safe="")
        frames.append(
            {
                "name": filename,
                "thumbnail_url": "/api/projects/{}/tasks/{}/images/thumbnail/{}".format(
                    task.project_id, task.id, encoded
                ),
                "download_url": "/api/projects/{}/tasks/{}/images/download/{}".format(
                    task.project_id, task.id, encoded
                ),
            }
        )
        if len(frames) >= limit:
            break
    return frames


def task_payload(task, user=None, include_details=False):
    assets = [_asset_payload(task, asset) for asset in sorted(set(task.available_assets or []))]
    srs = get_srs_name_units_from_epsg_or_wkt(task.epsg, task.wkt)
    can_change = bool(user is not None and user.has_perm("change_project", task.project))
    can_delete = bool(user is not None and user.has_perm("delete_project", task.project))
    details = {}
    if include_details:
        details = {
            "frames": _task_frame_payload(task),
            "media": task.media if isinstance(task.media, list) else [],
        }
    return {
        "id": str(task.id),
        "project_id": str(task.project_id),
        "project_name": task.project.name,
        "name": task.name or str(task.id),
        "status": _task_state(task),
        "status_label": task.get_status_display() or "UNKNOWN",
        "status_code": task.status,
        "progress": task.running_progress if task.status == status_codes.RUNNING else task.upload_progress,
        "upload_progress": task.upload_progress,
        "running_progress": task.running_progress,
        "last_error": task.last_error or "",
        "created_at": task.created_at,
        "images_count": task.images_count,
        "media_count": len(task.media) if isinstance(task.media, list) else 0,
        "frame_count": task.images_count,
        "srs": srs,
        "extent": task.get_extent(),
        "available_assets": assets,
        "artifact_revision": artifact_revision(task),
        "viewer_urls": {
            "map": "/astrakriti/runs/{}/map/".format(task.id),
            "model": "/astrakriti/runs/{}/model/".format(task.id),
            "measurements": "/astrakriti/runs/{}/measurements/".format(task.id),
            "reports": "/astrakriti/runs/{}/reports/".format(task.id),
            "files": "/astrakriti/runs/{}/files/".format(task.id),
        },
        "native_urls": {
            "task": "/api/projects/{}/tasks/{}/".format(task.project_id, task.id),
            "cancel": "/api/projects/{}/tasks/{}/cancel/".format(task.project_id, task.id),
            "restart": "/api/projects/{}/tasks/{}/restart/".format(task.project_id, task.id),
            "output": "/api/projects/{}/tasks/{}/output/".format(task.project_id, task.id),
        },
        "permissions": {
            "change": can_change,
            "delete": can_delete,
        },
        **details,
    }


def _visible_projects(user):
    return get_objects_for_user(
        user,
        "view_project",
        Project,
        accept_global_perms=True,
    ).filter(deleting=False).order_by("-created_at")


def _project_payload(project, include_tasks=True, user=None):
    tasks = []
    if include_tasks:
        tasks = [
            task_payload(task, user=user)
            for task in project.task_set.all().order_by("-created_at")[:100]
        ]
    try:
        metadata = project.astrakriti_mission_metadata
        mission_metadata = {
            "location": metadata.location,
            "capture_context": metadata.capture_context,
            "provenance": metadata.provenance,
            "schema_revision": metadata.schema_revision,
            "recorded": True,
            "updated_at": metadata.updated_at,
        }
    except AstrakritiMissionMetadata.DoesNotExist:
        mission_metadata = {
            "location": "",
            "capture_context": "",
            "provenance": {},
            "schema_revision": 1,
            "recorded": False,
            "updated_at": None,
        }
    legacy_missions = list(
        AstrakritiLegacyLink.objects.filter(
            project=project,
            entity_type=AstrakritiLegacyLink.MISSION,
        ).values("legacy_id", "legacy_label", "mapping_state")[:25]
    )
    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description or "",
        "mission_metadata": mission_metadata,
        "legacy_mission_mappings": legacy_missions,
        "created_at": project.created_at,
        "task_count": project.task_set.count(),
        "permissions": {
            "change": bool(user is not None and user.has_perm("change_project", project)),
            "delete": bool(user is not None and user.has_perm("delete_project", project)),
        },
        "tasks": tasks,
        "links": {
            "overview": "/astrakriti/missions/{}/".format(project.id),
            "new_task": "/dashboard/",
        },
    }


def _health_payload(user):
    nodes = []
    try:
        visible_nodes = get_objects_for_user(
            user,
            "view_processingnode",
            ProcessingNode,
            accept_global_perms=True,
        )
    except Exception:
        visible_nodes = ProcessingNode.objects.none()

    for node in visible_nodes:
        nodes.append(
            {
                "id": node.id,
                "label": str(node),
                "status": "connected" if node.is_online() else "unavailable",
                "last_checked": node.last_refreshed,
                "engine": node.engine or "",
                "engine_version": node.engine_version or "",
            }
        )

    try:
        usage = shutil.disk_usage(settings.MEDIA_ROOT)
        storage = {
            "status": "connected",
            "free_bytes": usage.free,
            "total_bytes": usage.total,
        }
    except OSError:
        storage = {
            "status": "unavailable",
            "detail": "WebODM could not read storage capacity. Check the configured storage and filesystem permissions.",
        }

    if not nodes:
        node_status = "unavailable"
    elif all(node["status"] == "connected" for node in nodes):
        node_status = "connected"
    else:
        node_status = "degraded"

    # Health refreshes should fail fast when an optional companion is down;
    # preparation uploads use the longer client timeout separately.
    companion = AstrakritiCompanionClient(timeout=3).health_payload()
    return {
        "checked_at": timezone.now(),
        "webodm": {
            "status": "connected",
            "detail": "Authenticated WebODM request is serving this page.",
            "version": settings.VERSION,
            "admin_available": bool(user.is_staff),
        },
        "worker": {
            "status": "unknown",
            "detail": "This WebODM revision exposes task progress, not a supported global worker health endpoint.",
        },
        "processing_nodes": {"status": node_status, "nodes": nodes},
        "storage": storage,
        "astrakriti_companion": companion,
    }


def _context_links(task):
    if task is None:
        return []
    return [
        {
            "label": label,
            "url": "/astrakriti/runs/{}/{}".format(task.id, page),
            "page": page,
        }
        for page, label in RUN_PAGES
    ]


def _project_context_links(project, page):
    if project is None:
        return []
    links = [
        ("Overview", "overview", "mission"),
        ("Runs", "runs", "runs"),
        ("Artifacts", "artifacts", "artifacts"),
        ("Reports", "reports", "reports"),
        ("Files", "files", "files"),
    ]
    return [
        {
            "label": label,
            "url": "/astrakriti/missions/{}/{}".format(
                project.id, "" if target == "overview" else target + "/"
            ),
            "active": page == active_page,
        }
        for label, target, active_page in links
    ]


def _shell_data(request, page, project=None, task=None):
    projects = list(_visible_projects(request.user)[:100])
    project_payloads = [
        _project_payload(item, include_tasks=True, user=request.user) for item in projects
    ]
    all_tasks = [task_item for project_item in project_payloads for task_item in project_item["tasks"]]

    active = next(
        (item for item in all_tasks if item["status"] in ("queued", "processing")),
        None,
    )
    data = {
        "page": page,
        "page_label": PAGE_LABELS.get(page, "ASTRAKRITI3D"),
        "projects": project_payloads,
        "tasks": all_tasks,
        "active_task": active,
        "project": _project_payload(project, include_tasks=True, user=request.user) if project else None,
        "task": task_payload(task, user=request.user, include_details=True) if task else None,
        "health": _health_payload(request.user),
    }
    return data


def _check_shell_project_perms(request, project):
    try:
        check_project_perms(request, project)
    except NotFound as error:
        raise Http404 from error


@login_required
def shell_view(request, page="overview", project_pk=None, task_pk=None):
    project = None
    task = None

    if project_pk is not None:
        project = get_object_or_404(Project, pk=project_pk, deleting=False)
        _check_shell_project_perms(request, project)

    if task_pk is not None:
        task = get_object_or_404(Task.objects.select_related("project"), pk=task_pk)
        _check_shell_project_perms(request, task.project)
        project = task.project

    if task is not None and page == "overview":
        page = "run"
    elif project is not None and page == "overview":
        page = "mission"

    data = _shell_data(request, page, project=project, task=task)
    viewer_params = {}
    if task is not None and page == "map":
        viewer_params = {
            "map-items": _json([task.get_map_items()]),
            "title": task.name or str(task.id),
            "public": "false",
            "share-buttons": "true",
            "permissions": _json(get_permissions(request.user, task.project)),
            "project": _json(None),
            "basemaps": _json([]),
        }
    elif task is not None and page == "model":
        viewer_params = {
            "task": _json(task.get_model_display_params()),
            "title": task.name or str(task.id),
            "public": "false",
            "share-buttons": "true",
            "model-type": request.GET.get("t", "cloud"),
        }

    return render(
        request,
        "coreplugins/astrakriti3d/templates/app.html",
        {
            "title": data["page_label"],
            "page": page,
            "data_json": _json(data),
            "viewer_params": viewer_params,
            "context_links": _context_links(task),
            "project_links": _project_context_links(project, page) if task is None else [],
            "task_id": str(task.id) if task else "",
            "dsm_available": bool(task is not None and task.dsm_extent is not None),
            "task_srs": data["task"]["srs"] if data["task"] else {},
            "artifact_revision": data["task"]["artifact_revision"] if data["task"] else "",
        },
    )

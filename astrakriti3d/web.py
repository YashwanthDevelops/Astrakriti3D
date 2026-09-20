"""Read-only dashboard API backed by Astrakriti3D project records."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sqlite3
from urllib.parse import quote, urlsplit

from flask import Flask, jsonify, redirect, send_file

from .config import Config


ROOT = Path(__file__).resolve().parents[1]
JOB_DB = Path("runtime/jobs.sqlite3")
ACTIVE_JOB_STATES = {"received", "validating", "submitting", "submitted", "running", "collecting"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
STATUS_MAP = {
    "completed": "complete",
    "failed": "failed",
    "cancelled": "cancelled",
    "running": "processing",
    "collecting": "processing",
    "submitted": "processing",
    "submitting": "processing",
    "validating": "processing",
    "received": "processing",
}


class DashboardDataError(RuntimeError):
    """Raised when the persisted dashboard data cannot be read safely."""


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _read(path: str | Path, default=None):
    try:
        return json.loads(_resolve(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _sha(path: str | Path):
    digest = hashlib.sha256()
    try:
        with _resolve(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1_048_576), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _format_bytes(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "—"
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size_bytes)
    unit = 0
    while value >= 1024 and unit < len(units) - 1:
        value /= 1024
        unit += 1
    precision = 0 if unit == 0 else 1
    return f"{value:.{precision}f} {units[unit]}"


def _is_within(path: str | Path, directory: str | Path | None = None) -> bool:
    directory = ROOT if directory is None else directory
    try:
        _resolve(path).resolve().relative_to(_resolve(directory).resolve())
        return True
    except (OSError, ValueError):
        return False


def _decode(value, default):
    if value in (None, ""):
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _project_job(row: dict) -> bool:
    """Keep persisted project records, excluding test-run rows in the DB."""
    manifest = row.get("image_manifest")
    if not isinstance(manifest, list) or not manifest:
        return False
    paths = [item.get("path") for item in manifest if isinstance(item, dict) and item.get("path")]
    if not paths:
        return False
    # The shared runtime database has accumulated pytest rows from the test
    # suite. They are not application records and must never appear in the UI.
    if any("pytest-of-" in str(path).lower() for path in paths):
        return False
    return True


def _read_jobs() -> list[dict]:
    """Read JobStore rows without opening the database for writes."""
    db_path = _resolve(JOB_DB)
    if not db_path.is_file():
        return []
    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM jobs ORDER BY updated_at DESC").fetchall()
        connection.close()
    except sqlite3.Error as exc:
        raise DashboardDataError("The dashboard database could not be read.") from exc

    jobs = []
    for raw in rows:
        row = dict(raw)
        row["image_manifest"] = _decode(row.get("image_manifest"), [])
        row["options"] = _decode(row.get("options"), [])
        row["diagnostics"] = _decode(row.get("diagnostics"), None)
        row["artifacts"] = _decode(row.get("artifacts"), [])
        row["event_history"] = _decode(row.get("event_history"), [])
        if _project_job(row):
            jobs.append(row)
    return jobs


def _timestamp(value, fallback="—") -> str:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        return str(value)


def _job_state(job: dict) -> str:
    return str(job.get("state") or "unknown").lower()


def _job_status(job: dict) -> str:
    return STATUS_MAP.get(_job_state(job), "pending")


def _job_progress(job: dict) -> float | None:
    value = job.get("progress")
    if value is None:
        events = job.get("event_history") or []
        if events and isinstance(events[-1], dict):
            value = events[-1].get("progress")
    try:
        return round(max(0.0, min(1.0, float(value))) * 100, 2) if value is not None else None
    except (TypeError, ValueError):
        return None


def _job_paths(job: dict) -> list[Path]:
    paths = []
    for item in job.get("image_manifest") or []:
        if isinstance(item, dict) and item.get("path"):
            paths.append(_resolve(item["path"]))
    return paths


def _job_run_label(job: dict) -> str | None:
    values = []
    for path in _job_paths(job):
        values.append(path.as_posix())
    for item in job.get("artifacts") or []:
        if isinstance(item, dict) and item.get("path"):
            values.append(str(item["path"]).replace("\\", "/"))
    for value in values:
        match = re.search(r"(?:^|/)(r\d+)(?:/|-|_|$)", value, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def _mission_name(job: dict) -> str:
    # JobStore persists the WebODM project id and image manifest, not a
    # separate mission-name column. Prefer the real source-video identity when
    # the project contains one; otherwise retain the persisted project id.
    video_files = sorted((_resolve("inputs")).glob("*.mp4"))
    if len(video_files) == 1:
        return video_files[0].stem.upper()
    project_id = job.get("project_id")
    if project_id not in (None, ""):
        return f"PROJECT {project_id}"
    return "UNASSIGNED PROJECT"


def _job_name(job: dict) -> str:
    label = _job_run_label(job)
    return f"{_mission_name(job)} · {label}" if label else _mission_name(job)


def _webodm_viewer_url(job: dict) -> str | None:
    """Return a credential-free link to the native WebODM task viewer."""
    base_url = os.environ.get("WEBODM_BASE_URL", "").strip().rstrip("/")
    project_id = job.get("project_id")
    task_id = job.get("task_id")
    if not base_url or project_id in (None, "") or task_id in (None, ""):
        return None
    return f"{base_url}/map/project/{quote(str(project_id), safe='')}/task/{quote(str(task_id), safe='')}/"


def _stage_label(job: dict) -> str:
    state = _job_state(job)
    labels = {
        "received": "RECEIVED",
        "validating": "VALIDATING INPUT",
        "submitting": "SUBMITTING TO WEBODM",
        "submitted": "SUBMITTED TO WEBODM",
        "running": "WEBODM PROCESSING",
        "collecting": "COLLECTING ARTIFACTS",
        "completed": "COMPLETED",
        "failed": "PROCESSING FAILED",
        "cancelled": "CANCELLED",
    }
    return labels.get(state, state.replace("_", " ").upper() or "UNKNOWN")


def _candidate_metadata_paths(job: dict) -> list[Path]:
    candidates = []
    seen = set()
    for source in _job_paths(job):
        current = source.parent
        while _is_within(current):
            for name in ("association_manifest.json", "geo.txt"):
                candidate = current / name
                if candidate not in seen:
                    candidates.append(candidate)
                    seen.add(candidate)
            telemetry = current / "telemetry" / "association_manifest.json"
            if telemetry not in seen:
                candidates.append(telemetry)
                seen.add(telemetry)
            if current == _resolve(ROOT):
                break
            current = current.parent
    return candidates


def _telemetry_count(job: dict) -> int | None:
    manifest = job.get("image_manifest") or []
    embedded = [item for item in manifest if isinstance(item, dict) and item.get("telemetry_record_id")]
    if embedded:
        return len(embedded)
    for candidate in _candidate_metadata_paths(job):
        if candidate.name == "association_manifest.json":
            data = _read(candidate)
            if isinstance(data, dict) and isinstance(data.get("rows"), list):
                return len(data["rows"])
        elif candidate.name == "geo.txt" and candidate.is_file():
            try:
                records = [line for line in candidate.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
            except OSError:
                records = []
            if records:
                return len(records)
    return None


def _artifact_records(job: dict) -> list[dict]:
    records = []
    for item in job.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        raw_path = item.get("path") or item.get("name")
        if not raw_path:
            continue
        path = _resolve(raw_path)
        exists = path.is_file()
        size = path.stat().st_size if exists else None
        name = str(item.get("name") or path.name)
        records.append(
            {
                "name": name,
                "label": name,
                "format": path.suffix.lstrip(".").upper() or "FILE",
                "path": str(path),
                "exists": exists,
                "size_bytes": size,
                "size_label": _format_bytes(size),
                "sha256": _sha(path) if exists else item.get("sha256"),
                "declared_sha256": item.get("sha256"),
                "run_id": job.get("local_id"),
                "data_source": "runtime/jobs.sqlite3",
            }
        )
    return records


def _preview_path(job: dict, kind: str) -> Path | None:
    needle = "ortho" if kind == "orthophoto" else "point"
    records = _artifact_records(job)
    for record in records:
        path = Path(record["path"])
        if record["exists"] and path.suffix.lower() in IMAGE_SUFFIXES and needle in path.name.lower():
            return path
    # A real preview may sit beside a recorded artifact. Never use a UI
    # placeholder here: if no browser-readable preview exists, return None.
    parents = {Path(record["path"]).parent for record in records}
    for parent in parents:
        if not parent.is_dir() or not _is_within(parent):
            continue
        for candidate in sorted(parent.glob("*preview*")):
            if candidate.is_file() and candidate.suffix.lower() in IMAGE_SUFFIXES and needle in candidate.name.lower():
                return candidate
    return None


def _media_descriptor(job: dict, kind: str) -> dict:
    path = _preview_path(job, kind)
    label = "ORTHOPHOTO / PROJECT PREVIEW" if kind == "orthophoto" else "POINT CLOUD / ELEVATION PREVIEW"
    if path is None:
        return {
            "src": "",
            "label": label,
            "meta": "No preview artifact available",
            "placeholder": False,
            "artifact_available": bool(_artifact_records(job)),
        }
    size = _format_bytes(path.stat().st_size)
    return {
        "src": f"/api/dashboard/media/{job.get('local_id')}/{kind}",
        "label": label,
        "meta": f"{path.name} · {size}",
        "placeholder": False,
        "artifact_available": True,
        "path": str(path),
    }


def _pipeline(job: dict) -> list[dict]:
    progress = _job_progress(job)
    value = f"{progress:g}%" if progress is not None else "—"
    return [{
        "label": "WEBODM TASK",
        "status": "processing" if _job_state(job) in ACTIVE_JOB_STATES else _job_status(job),
        "value": value,
    }]


def _dashboard_artifacts(jobs: list[dict]) -> list[dict]:
    rows = []
    for job in jobs:
        records = _artifact_records(job)
        if not records:
            continue
        rows.extend(records)
        if len(rows) >= 4:
            break
    return rows[:4]


def _dashboard_notices(jobs: list[dict]) -> list[dict]:
    notices = []
    for job in jobs:
        state = _job_state(job)
        run_id = str(job.get("local_id") or "unknown run")
        updated = _timestamp(job.get("updated_at"))
        diagnostics = job.get("diagnostics") if isinstance(job.get("diagnostics"), dict) else {}
        if state == "failed":
            detail = str(diagnostics.get("error") or diagnostics.get("message") or "The persisted run entered a failed state.")
            notices.append({"kind": "failed", "run_id": run_id, "title": f"Run {run_id} failed", "detail": detail, "timestamp": updated})
        elif state == "cancelled":
            notices.append({"kind": "warning", "run_id": run_id, "title": f"Run {run_id} cancelled", "detail": "Processing was stopped before completion.", "timestamp": updated})
        elif state == "completed" and any(not artifact["exists"] for artifact in _artifact_records(job)):
            notices.append({"kind": "warning", "run_id": run_id, "title": f"Run {run_id} has missing artifacts", "detail": "One or more recorded outputs are unavailable on disk.", "timestamp": updated})
        if len(notices) >= 4:
            break
    return notices


def _dashboard_utility(jobs: list[dict]) -> dict:
    storage = {"label": "Storage status unavailable", "status": "neutral"}
    try:
        usage = shutil.disk_usage(_resolve(ROOT))
        ratio = usage.free / usage.total if usage.total else 0
        storage = {
            "label": f"{_format_bytes(usage.free)} free",
            "status": "warning" if ratio < 0.10 else "healthy",
        }
    except OSError:
        pass

    active = next((job for job in jobs if _job_state(job) in ACTIVE_JOB_STATES), None)
    has_task_history = any(job.get("task_id") for job in jobs)
    webodm = {
        "label": "WebODM task history available" if has_task_history else "WebODM status unavailable",
        "status": "neutral",
    }
    worker = {
        "label": f"Worker state: {_job_state(active)}" if active else "Worker status unavailable",
        "status": "processing" if active else "neutral",
    }
    return {
        "system_health": {"label": "SYSTEM HEALTH UNAVAILABLE", "status": "neutral"},
        "webodm": webodm,
        "worker": worker,
        "storage": storage,
        "timestamp": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


def _dashboard_data(summary: dict, jobs: list[dict] | None = None) -> dict:
    jobs = _read_jobs() if jobs is None else jobs
    active_jobs = [job for job in jobs if _job_state(job) in ACTIVE_JOB_STATES]
    active_job = active_jobs[0] if active_jobs else None
    dashboard_artifacts = _dashboard_artifacts(jobs)
    entity_counts = {
        "missions": len({_mission_name(job) for job in jobs}),
        "runs": len(jobs),
        "artifacts": sum(len(_artifact_records(job)) for job in jobs),
    }
    summary_data = {
        "active": len(active_jobs),
        "completed": sum(1 for job in jobs if _job_state(job) == "completed"),
        "failed": sum(1 for job in jobs if _job_state(job) == "failed"),
    }

    if not any(entity_counts.values()):
        state = "first_use"
    elif active_job:
        state = "active_processing"
    else:
        state = "no_active"

    active = None
    if active_job:
        progress = _job_progress(active_job)
        active = {
            "id": active_job.get("local_id"),
            "mission": _mission_name(active_job),
            "subtitle": f"{len(active_job.get('image_manifest') or [])} input frames · {_job_name(active_job)}",
            "stage": _stage_label(active_job),
            "status": _job_status(active_job),
            "webodm_task_id": active_job.get("task_id"),
            "webodm_viewer_url": _webodm_viewer_url(active_job),
            "progress": progress,
            "frame_count": len(active_job.get("image_manifest") or []),
            "telemetry_count": _telemetry_count(active_job),
            "started": f"started {_timestamp(active_job.get('created_at'))}",
            "media": {
                "orthophoto": _media_descriptor(active_job, "orthophoto"),
                "point_cloud": _media_descriptor(active_job, "point_cloud"),
            },
            "pipeline": _pipeline(active_job),
        }

    recent = []
    for job in jobs[:4]:
        recent.append({
            "id": job.get("local_id"),
            "name": _job_name(job),
            "status": _job_status(job),
            "updated": _timestamp(job.get("updated_at")),
            "frame_count": len(job.get("image_manifest") or []),
            "webodm_task_id": job.get("task_id"),
            "webodm_viewer_url": _webodm_viewer_url(job),
        })

    latest_run = None
    if jobs:
        latest_job = jobs[0]
        latest_artifacts = _artifact_records(latest_job)
        latest_run = {
            "id": latest_job.get("local_id"),
            "name": _job_name(latest_job),
            "status": _job_status(latest_job),
            "updated": _timestamp(latest_job.get("updated_at")),
            "available_outputs": [artifact["label"] for artifact in latest_artifacts if artifact["exists"]],
        }

    return {
        "state": state,
        "utility": _dashboard_utility(jobs),
        "summary": summary_data,
        "entity_counts": entity_counts,
        "active_run": active,
        "latest_run": latest_run,
        "recent_reconstructions": recent,
        "artifacts": dashboard_artifacts,
        "notices": _dashboard_notices(jobs),
        "empty_sections": {
            "recent": "No Runs have been created yet." if not jobs else "No reconstruction history is available.",
            "artifacts": "Artifacts will appear here after the first successful Run." if not jobs else "No artifacts available.",
            "notices": "No active notices.",
        },
        "empty_state": {
            "title": "NO ACTIVE RECONSTRUCTION",
            "body": "No reconstruction is currently processing.",
            "detail": "Start a new reconstruction when you are ready.",
            "action": "NEW RECONSTRUCTION →",
        },
        "first_use_state": {
            "title": "NO RECONSTRUCTIONS YET",
            "body": "Create your first reconstruction workspace.",
            "detail": "Start by creating a Mission, adding a source video, optionally adding telemetry, and reviewing the preflight checks before processing begins.",
            "action": "NEW RECONSTRUCTION →",
            "setup_steps": [
                {"number": "01", "label": "CREATE OR SELECT MISSION"},
                {"number": "02", "label": "ADD SOURCE VIDEO"},
                {"number": "03", "label": "ADD TELEMETRY"},
                {"number": "04", "label": "REVIEW PREFLIGHT"},
                {"number": "05", "label": "START RECONSTRUCTION"},
            ],
        },
        "real_evidence": {
            "baseline": summary.get("project", {}).get("production_baseline"),
            "frames": summary.get("frames", {}).get("count", 0),
            "telemetry": summary.get("telemetry", {}).get("count", 0),
            "telemetry_matched": summary.get("telemetry", {}).get("matched", 0),
            "validation": summary.get("validation", {}),
            "artifacts_present": sum(1 for item in summary.get("artifacts", []) if item.get("exists")),
            "data_source": str(_resolve(JOB_DB)),
        },
    }


def build_summary():
    phase2 = _read(Path("evidence/phase2/real-run/manifest.json"), {}) or {}
    association = _read(Path("evidence/phase3/real-run/association_manifest.json"), {}) or {}
    inventory = _read(Path("evidence/phase5/baseline/baseline_inventory.json"), {}) or {}
    evaluation = _read(Path("evidence/phase7/r1-evaluation-20260915/phase7_evaluation.json"), {}) or {}

    rows = association.get("rows", [])
    matched = sum(1 for item in rows if item.get("association_status") == "matched")
    artifacts = []
    for artifact in inventory.get("artifacts", []):
        path = artifact.get("path", "")
        resolved = _resolve(path)
        artifacts.append(
            {
                "name": artifact.get("name"),
                "path": str(resolved),
                "exists": resolved.is_file(),
                "sha256": _sha(resolved),
                "declared_sha256": artifact.get("sha256"),
                "hash_match": resolved.is_file() and _sha(resolved) == artifact.get("sha256"),
                "size_bytes": resolved.stat().st_size if resolved.is_file() else None,
            }
        )

    summary = {
        "project": {
            "name": "Astrakriti3D",
            "production_baseline": "R1",
            "baseline_images": len(phase2.get("frames", [])),
        },
        "frames": {
            "count": len(phase2.get("frames", [])),
            "source_video": phase2.get("video", {}).get("video_path"),
            "source_video_hash": _sha(ROOT / "inputs/DJI_0142.MP4"),
        },
        "telemetry": {
            "count": len(rows),
            "matched": matched,
            "status": "verified" if rows and matched == len(rows) else "incomplete",
        },
        "geolocation": {
            "status": "verified",
            "crs": "EPSG:4326",
            "route": "odm_geo_txt",
            "path": str((ROOT / "evidence/phase4/real-run/geo.txt").resolve()),
            "hash": _sha(ROOT / "evidence/phase4/real-run/geo.txt"),
        },
        "reconstruction": {
            "status": "completed",
            "task_id": inventory.get("task", {}).get("task_id"),
            "local_job_id": inventory.get("task", {}).get("local_job_id"),
            "production": "R1",
            "experimental": {
                "R2": "unpromoted; invalid coordinate provenance",
                "R3": "experimental; all-frame fallback",
            },
        },
        "validation": {
            "accuracy": evaluation.get("accuracy", {}).get("status", "unverified"),
            "scale": evaluation.get("relative_shape_and_dimensions", {}).get("status", "unknown_scale"),
            "completeness": evaluation.get("completeness", {}).get("status", "audit_template"),
        },
        "artifacts": artifacts,
        "read_only": True,
    }
    summary["dashboard"] = _dashboard_data(summary)
    return summary


def _webodm_shell_url():
    """Return a validated WebODM shell URL, never a credential-bearing redirect."""
    base_url = Config.from_env().base_url.strip()
    if not base_url or any(ord(character) < 32 or ord(character) == 127 for character in base_url):
        return None
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        return None
    return base_url.rstrip("/") + "/astrakriti/overview/"


def create_app():
    # Keep the read-only compatibility API, but do not serve the superseded UI assets.
    app = Flask(__name__, static_folder=None)

    @app.get("/api/summary")
    def summary():
        try:
            return jsonify(build_summary())
        except DashboardDataError as exc:
            return jsonify({"error": str(exc)}), 503

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "available",
                "engine": "WebODM hidden; read-only project data view",
                "webodm_credentials_exposed": False,
            }
        )

    @app.get("/api/artifacts")
    def artifacts():
        try:
            return jsonify(build_summary()["artifacts"])
        except DashboardDataError as exc:
            return jsonify({"error": str(exc)}), 503

    @app.get("/api/dashboard/media/<run_id>/<kind>")
    def dashboard_media(run_id: str, kind: str):
        if kind not in {"orthophoto", "point_cloud"}:
            return jsonify({"error": "Unknown preview type."}), 404
        try:
            job = next((item for item in _read_jobs() if str(item.get("local_id")) == run_id), None)
        except DashboardDataError as exc:
            return jsonify({"error": str(exc)}), 503
        if job is None:
            return jsonify({"error": "Run not found."}), 404
        path = _preview_path(job, kind)
        if path is None or not _is_within(path) or path.suffix.lower() not in IMAGE_SUFFIXES:
            return jsonify({"error": "No browser-readable preview artifact is available."}), 404
        return send_file(path, mimetype=mimetypes.guess_type(path.name)[0], conditional=True)

    @app.get("/")
    def index():
        target = _webodm_shell_url()
        if target:
            return redirect(target, code=302)
        return jsonify(
            {
                "error": "standalone_dashboard_retired",
                "detail": "Open ASTRAKRITI3D inside customized WebODM. Configure a valid WEBODM_BASE_URL to enable this redirect.",
            }
        ), 410

    return app


app = create_app()

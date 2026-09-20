"""Protected preparation-only service for the WebODM integration boundary.

This module intentionally does not expose the legacy dashboard or a second
reconstruction lifecycle. It accepts an authenticated source video/SRT,
delegates preparation to the existing Astrakriti queue, and exposes only the
resulting preparation status and bundle for the WebODM plugin to consume.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import threading
import zipfile

from flask import Flask, jsonify, request, send_file
from werkzeug.utils import secure_filename

from .orchestrator import PreparationQueue


JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
SRT_SUFFIXES = {".srt"}


class CompanionRequestError(ValueError):
    """A client-visible but non-sensitive companion request error."""


class CompanionSubmissionStore:
    """Small durable request index kept separate from the legacy JobStore."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._records = self._load()

    def _load(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _save(self) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._records, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            value = self._records.get(job_id)
            return dict(value) if isinstance(value, dict) else None

    def put(self, job_id: str, value: dict) -> None:
        with self._lock:
            self._records[job_id] = dict(value)
            self._save()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_job_id(value: str | None) -> str:
    value = str(value or "")
    if not JOB_ID_RE.fullmatch(value):
        raise CompanionRequestError("job_id must be a 16–128 character idempotency identity")
    return value


def _safe_upload_name(value: str | None, suffixes: set[str], label: str) -> str:
    name = secure_filename(value or "")
    suffix = Path(name).suffix.lower()
    if not name or suffix not in suffixes:
        raise CompanionRequestError(f"{label} must use a supported file type")
    return name


def _zip_member_safe(name: str) -> bool:
    path = Path(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name


def _write_bundle(output: Path) -> Path:
    bundle = output / "prepared-input.zip"
    if bundle.is_file():
        return bundle
    temporary = output / "prepared-input.zip.tmp"
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if not path.is_file() or path == temporary or path == bundle or path.is_symlink():
                continue
            relative = path.relative_to(output).as_posix()
            if not _zip_member_safe(relative):
                raise CompanionRequestError("preparation produced an unsafe bundle path")
            archive.write(path, relative)
    os.replace(temporary, bundle)
    return bundle


def _copy_upload(upload, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".uploading")
    upload.save(str(temporary))
    os.replace(temporary, destination)


def _authorization_ok(expected: str, provided: str | None) -> bool:
    if not expected or not provided or not provided.startswith("Bearer "):
        return False
    return hmac.compare_digest(expected, provided[7:].strip())


def _status_payload(job_id: str, record: dict, queue: PreparationQueue) -> dict:
    try:
        status = queue.status(job_id)
    except KeyError:
        status = {"status": "recovery_required"}
    output = Path(record["output"])
    payload = {
        "job_id": job_id,
        "status": status.get("status", "unknown"),
        "mode": record.get("mode"),
        "created_at": status.get("created_at"),
        "error": status.get("error"),
        "result": status.get("result"),
    }
    if payload["status"] == "completed" and output.is_dir():
        payload["bundle_available"] = True
        payload["bundle_name"] = "prepared-input.zip"
    else:
        payload["bundle_available"] = False
    return payload


def create_companion_app(*, root: str | Path | None = None, token: str | None = None, queue=None):
    """Build the preparation-only Flask service.

    ``root``, ``token``, and ``queue`` are injectable for isolated tests. In
    production they default to environment configuration and a persistent
    queue under ``ASTRAKRITI_COMPANION_ROOT``.
    """

    root_path = Path(root or os.environ.get("ASTRAKRITI_COMPANION_ROOT", "runtime/companion")).resolve()
    root_path.mkdir(parents=True, exist_ok=True)
    expected_token = token if token is not None else os.environ.get("ASTRAKRITI_COMPANION_TOKEN", "")
    preparation_queue = queue or PreparationQueue(root_path / "preparation_jobs.json")
    submissions = CompanionSubmissionStore(root_path / "submissions.json")
    app = Flask(__name__)
    app.config["ASTRAKRITI_COMPANION_ROOT"] = root_path
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("ASTRAKRITI_COMPANION_MAX_BYTES", str(8 * 1024**3)))

    def authorized():
        if not expected_token:
            return jsonify({"status": "not_configured", "detail": "Companion authentication is not configured."}), 503
        if not _authorization_ok(expected_token, request.headers.get("Authorization")):
            return jsonify({"status": "unauthorized"}), 401
        return None

    @app.get("/health")
    def health():
        denied = authorized()
        if denied:
            return denied
        return jsonify({"status": "ready", "service": "astrakriti-preparation", "preparation_only": True})

    @app.post("/v1/preparations")
    def create_preparation():
        denied = authorized()
        if denied:
            return denied
        try:
            job_id = _safe_job_id(request.form.get("job_id"))
            mode = (request.form.get("mode") or "local").strip().lower()
            if mode not in {"local", "georeferenced"}:
                raise CompanionRequestError("mode must be local or georeferenced")
            video = request.files.get("video")
            srt = request.files.get("srt")
            if video is None:
                raise CompanionRequestError("video is required")
            video_name = _safe_upload_name(video.filename, VIDEO_SUFFIXES, "video")
            srt_name = _safe_upload_name(srt.filename, SRT_SUFFIXES, "SRT") if srt else None
            if mode == "georeferenced" and srt is None:
                raise CompanionRequestError("georeferenced mode requires an SRT file")

            existing = submissions.get(job_id)
            job_root = root_path / "jobs" / job_id
            source_root = job_root / "source"
            output = job_root / "prepared"
            video_path = source_root / video_name
            srt_path = source_root / srt_name if srt_name else None

            if existing is not None:
                if existing.get("mode") != mode:
                    raise CompanionRequestError("job_id is already bound to a different mode")
                retry_video = source_root / (".retry-" + video_name)
                retry_srt = source_root / (".retry-" + srt_name) if srt_name else None
                _copy_upload(video, retry_video)
                if srt is not None:
                    _copy_upload(srt, retry_srt)
                try:
                    if existing.get("video_sha256") != _sha256(retry_video):
                        raise CompanionRequestError("job_id is already bound to a different video")
                    if existing.get("srt_sha256") != (_sha256(retry_srt) if retry_srt else None):
                        raise CompanionRequestError("job_id is already bound to a different SRT")
                finally:
                    retry_video.unlink(missing_ok=True)
                    if retry_srt:
                        retry_srt.unlink(missing_ok=True)
                return jsonify(_status_payload(job_id, existing, preparation_queue)), 202

            _copy_upload(video, video_path)
            if srt is not None:
                _copy_upload(srt, srt_path)
            record = {
                "job_id": job_id,
                "mode": mode,
                "video": str(video_path),
                "video_sha256": _sha256(video_path),
                "srt": str(srt_path) if srt_path else None,
                "srt_sha256": _sha256(srt_path) if srt_path else None,
                "output": str(output),
            }
            submissions.put(job_id, record)
            try:
                preparation_queue.submit(
                    job_id,
                    video_path,
                    output,
                    mode=mode,
                    srt=srt_path,
                )
            except ValueError:
                # The durable queue may have loaded the job between the index
                # write and this request; status remains the authority.
                pass
            return jsonify(_status_payload(job_id, record, preparation_queue)), 202
        except CompanionRequestError as exc:
            return jsonify({"status": "invalid", "detail": str(exc)}), 400
        except OSError as exc:
            return jsonify({"status": "unavailable", "detail": "Companion storage is unavailable."}), 503

    @app.get("/v1/preparations/<job_id>")
    def preparation_status(job_id):
        denied = authorized()
        if denied:
            return denied
        try:
            job_id = _safe_job_id(job_id)
        except CompanionRequestError as exc:
            return jsonify({"status": "invalid", "detail": str(exc)}), 400
        record = submissions.get(job_id)
        if record is None:
            return jsonify({"status": "not_found"}), 404
        return jsonify(_status_payload(job_id, record, preparation_queue))

    @app.get("/v1/preparations/<job_id>/bundle")
    def preparation_bundle(job_id):
        denied = authorized()
        if denied:
            return denied
        record = submissions.get(job_id)
        if record is None:
            return jsonify({"status": "not_found"}), 404
        status_payload = _status_payload(job_id, record, preparation_queue)
        if status_payload["status"] != "completed":
            return jsonify({"status": status_payload["status"], "detail": "Preparation is not complete."}), 409
        try:
            bundle = _write_bundle(Path(record["output"]))
        except (CompanionRequestError, OSError, ValueError) as exc:
            return jsonify({"status": "unavailable", "detail": str(exc)}), 503
        return send_file(bundle, as_attachment=True, download_name="prepared-input.zip", mimetype="application/zip")

    @app.post("/v1/preparations/<job_id>/cancel")
    def cancel_preparation(job_id):
        denied = authorized()
        if denied:
            return denied
        record = submissions.get(job_id)
        if record is None:
            return jsonify({"status": "not_found"}), 404
        try:
            result = preparation_queue.cancel(_safe_job_id(job_id))
        except (KeyError, CompanionRequestError):
            return jsonify({"status": "not_found"}), 404
        except ValueError as exc:
            return jsonify({"status": "invalid", "detail": str(exc)}), 409
        return jsonify(_status_payload(job_id, record, preparation_queue) | {"queue": result})

    return app

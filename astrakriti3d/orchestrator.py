"""Unified run orchestration for preflight, preparation, and reconstruction."""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .preflight import run_preflight
from .project import prepare_project, ProjectPreparationError
from .recovery import run_reconstruction


class RunOrchestrationError(RuntimeError):
    pass


class PreparationQueue:
    """Persistent, non-blocking queue for Phase 4 preparation jobs."""

    def __init__(self, state_path):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="astrakriti3d-prep")
        self._jobs = {}
        if self.state_path.is_file():
            self._jobs = json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save(self):
        self.state_path.write_text(json.dumps(self._jobs, indent=2), encoding="utf-8")

    def submit(self, job_id, video, output, *, mode, srt=None, **options):
        with self._lock:
            if job_id in self._jobs and self._jobs[job_id]["status"] not in {"failed", "cancelled"}:
                raise ValueError(f"preparation job already exists: {job_id}")
            self._jobs[job_id] = {"status": "queued", "created_at": datetime.now(timezone.utc).isoformat(), "video": str(Path(video).resolve()), "output": str(Path(output).resolve()), "mode": mode, "srt": str(Path(srt).resolve()) if srt else None}
            self._save()

        def work():
            with self._lock:
                if self._jobs[job_id]["status"] == "cancelled":
                    return
                self._jobs[job_id]["status"] = "running"
                self._save()
            try:
                result = prepare_project(video, output, mode=mode, srt=srt, **options)
                with self._lock:
                    self._jobs[job_id].update({"status": "completed", "result": result.get("project_report", {})})
                    self._save()
            except Exception as exc:
                with self._lock:
                    self._jobs[job_id].update({"status": "failed", "error": str(exc)})
                    self._save()

        self._executor.submit(work)
        return self.status(job_id)

    def cancel(self, job_id):
        with self._lock:
            job = self._jobs[job_id]
            if job["status"] == "queued":
                job["status"] = "cancelled"
                self._save()
                return self.status(job_id)
            raise ValueError("running preparation cannot be safely cancelled")

    def status(self, job_id):
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return dict(self._jobs[job_id])


def _validate_prepared_input(output: Path, mode: str) -> dict:
    manifest_path = output / "manifest.json"
    frames_dir = output / "frames"
    if not manifest_path.is_file():
        raise RunOrchestrationError(f"preparation did not create manifest.json: {manifest_path}")
    if not frames_dir.is_dir():
        raise RunOrchestrationError(f"preparation did not create frames directory: {frames_dir}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunOrchestrationError(f"prepared manifest is unreadable: {exc}") from exc
    frames = manifest.get("frames")
    if not isinstance(frames, list) or not frames:
        raise RunOrchestrationError("prepared manifest contains no frames")
    names = [str(frame.get("output_filename", "")) for frame in frames]
    if any(not name or Path(name).name != name for name in names):
        raise RunOrchestrationError("prepared manifest contains invalid frame filenames")
    if len(names) != len(set(names)) or names != sorted(names):
        raise RunOrchestrationError("prepared frame filenames must be unique and ordered")
    timestamps = [frame.get("source_timestamp_seconds") for frame in frames]
    try:
        if any(float(a) >= float(b) for a, b in zip(timestamps, timestamps[1:])):
            raise RunOrchestrationError("prepared frame timestamps must be strictly increasing")
    except (TypeError, ValueError) as exc:
        raise RunOrchestrationError("prepared frame timestamps are invalid") from exc
    missing = [name for name in names if not (frames_dir / name).is_file()]
    if missing:
        raise RunOrchestrationError(f"prepared frames are missing: {missing[:5]}")
    if mode == "local":
        forbidden = [str(p) for p in (output / "geo.txt", output / "telemetry") if p.exists()]
        if forbidden:
            raise RunOrchestrationError("local preparation produced geographic inputs: " + ", ".join(forbidden))
    else:
        if not (output / "geo.txt").is_file():
            raise RunOrchestrationError("georeferenced preparation did not create geo.txt")
    return {"manifest": str(manifest_path.resolve()), "frames": str(frames_dir.resolve()), "frame_count": len(frames), "mode": mode}


def run_pipeline(video, output, *, mode, srt=None, preflight_fn=run_preflight,
                 prepare_fn=prepare_project, reconstruct_fn=run_reconstruction,
                 cancel_after=None, poll_seconds=3.0):
    """Run the supported production stages in order without overwriting output."""
    if mode not in {"local", "georeferenced"}:
        raise RunOrchestrationError("mode must be local or georeferenced")
    if mode == "georeferenced" and not srt:
        raise RunOrchestrationError("--mode georeferenced requires --srt PATH")
    video_path = Path(video).resolve()
    output_path = Path(output).resolve()
    if output_path.exists():
        raise RunOrchestrationError(f"output already exists; choose a new run directory: {output_path}")

    preflight = preflight_fn(video_path, output_path / "preflight", mode=mode, srt=srt)
    result = {"ok": False, "mode": mode, "video": str(video_path), "output": str(output_path), "preflight": preflight}
    if preflight.get("status") != "PASS":
        result["stage"] = "preflight"
        result["error"] = "preflight failed; preparation and reconstruction were not started"
        return result
    try:
        preparation = prepare_fn(video_path, output_path, mode=mode, srt=srt)
        result["preparation"] = {"mode": preparation.get("mode"), "image_count": preparation.get("project_report", {}).get("image_count"), "manifest": preparation.get("manifest", {})}
        prepared = _validate_prepared_input(output_path, mode)
        result["prepared_input"] = prepared
    except (ProjectPreparationError, OSError, ValueError, RunOrchestrationError) as exc:
        result.update({"stage": "preparation", "error": str(exc)})
        return result
    except Exception as exc:
        result.update({"stage": "preparation", "error": str(exc)})
        return result
    reconstruction = reconstruct_fn(video_path, prepared["frames"], output_path / "webodm", mode=mode, srt=srt, geo_txt=str(output_path / "geo.txt") if mode == "georeferenced" else None, cancel_after=cancel_after, poll_seconds=poll_seconds)
    result["reconstruction"] = reconstruction
    result["ok"] = bool(reconstruction.get("ok"))
    result["stage"] = "completed" if result["ok"] else "reconstruction"
    return result

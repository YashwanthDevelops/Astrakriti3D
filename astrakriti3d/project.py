"""Mode-aware project preparation for local and georeferenced workflows."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

from .video import prepare_video
from .telemetry import inspect_metadata, TelemetryError
from .geolocation import prepare_geolocation, GeolocationError

class ProjectPreparationError(RuntimeError):
    pass

def _write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

def prepare_project(video, output, *, mode=None, srt=None, interval_seconds=1.0,
                    extraction_mode="seek", tolerance=0.5, time_offset=0.0):
    """Prepare a WebODM input with explicit provenance mode.

    Omitting ``mode`` deliberately selects local mode. SRT is ignored in that
    mode, and no geo.txt or telemetry files are created.
    """
    selected_mode = mode or "local"
    if selected_mode not in {"local", "georeferenced"}:
        raise ProjectPreparationError("mode must be 'local' or 'georeferenced'")
    video_path = Path(video)
    out = Path(output)
    if not video_path.is_file():
        raise ProjectPreparationError(f"video does not exist: {video_path}")
    if selected_mode == "georeferenced" and not srt:
        raise ProjectPreparationError("--mode georeferenced requires --srt PATH; provide valid DJI telemetry/SRT")
    # Never mix a new local run with stale geographic inputs from an earlier run.
    stale = [p for p in (out / "geo.txt", out / "geolocation_report.json", out / "telemetry") if p.exists()]
    if stale:
        raise ProjectPreparationError("output contains existing geographic data; use a new output directory to prevent stale telemetry: " + ", ".join(str(p) for p in stale))
    report = prepare_video(video_path, out, interval_seconds=interval_seconds, extraction_mode=extraction_mode)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({"mode": selected_mode, "georeferenced": selected_mode == "georeferenced", "telemetry": None, "geo_txt": None})
    final = {"schema_version": "astrakriti3d.project-preparation.v1", "mode": selected_mode, "georeferenced": selected_mode == "georeferenced", "source_video": str(video_path.resolve()), "source_video_sha256": hashlib.sha256(video_path.read_bytes()).hexdigest(), "absolute_position_available": selected_mode == "georeferenced", "crs": "EPSG:4326" if selected_mode == "georeferenced" else None, "gps_residuals_available": selected_mode == "georeferenced", "geographic_orientation_available": selected_mode == "georeferenced", "image_count": report["output_count"], "manifest": str(manifest_path.resolve())}
    if selected_mode == "local":
        final.update({"route": "local_unreferenced", "telemetry": None, "geo_txt": None, "warnings": ["SRT/telemetry was not used.", "Absolute geographic position, CRS, GPS residuals, and geographic orientation are unavailable.", "Downstream WebODM submission must omit geo.txt/GCP inputs."]})
        _write_manifest(manifest_path, manifest)
    else:
        srt_path = Path(srt)
        if not srt_path.is_file():
            raise ProjectPreparationError(f"SRT does not exist: {srt_path}; provide a valid telemetry file")
        telemetry_dir = out / "telemetry"
        try:
            telemetry_report = inspect_metadata(video_path, srt_path, manifest_path, telemetry_dir, tolerance, time_offset)
        except (TelemetryError, ValueError) as exc:
            raise ProjectPreparationError(f"invalid SRT/telemetry: {exc}") from exc
        if telemetry_report["srt"]["invalid_record_count"] or telemetry_report["srt"].get("errors"):
            raise ProjectPreparationError("invalid SRT/telemetry records; georeferenced preparation requires every parsed record to be valid")
        if telemetry_report["association"]["matched_count"] != telemetry_report["association"]["frame_count"]:
            raise ProjectPreparationError("telemetry association is incomplete; georeferenced preparation requires every frame to be matched")
        try:
            geo_report = prepare_geolocation(video_path, manifest_path, telemetry_dir / "association_manifest.json", out, tolerance)
        except (GeolocationError, ValueError) as exc:
            raise ProjectPreparationError(f"invalid georeferenced input: {exc}") from exc
        manifest.update({"mode": "georeferenced", "georeferenced": True, "telemetry": str((telemetry_dir / "association_manifest.json").resolve()), "geo_txt": str((out / "geo.txt").resolve())})
        final.update({"route": "odm_geo_txt", "telemetry": telemetry_report, "geo_txt": str((out / "geo.txt").resolve()), "warnings": geo_report.get("warnings", [])})
        _write_manifest(manifest_path, manifest)
    (out / "project_report.json").write_text(json.dumps(final, indent=2), encoding="utf-8")
    return {"mode": selected_mode, "manifest": manifest, "project_report": final}

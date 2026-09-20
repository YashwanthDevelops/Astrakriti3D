"""Mode-aware project preparation for local and georeferenced workflows."""
from __future__ import annotations
import hashlib, json
import tempfile
from pathlib import Path

from .video import prepare_video
from .telemetry import inspect_metadata, TelemetryError
from .geolocation import prepare_geolocation, GeolocationError
from .selection import adaptive_select_frames
from .coverage_selection import coverage_aware_select_streaming

class ProjectPreparationError(RuntimeError):
    pass

def _write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _selection_advisory(out: Path, mode: str) -> dict:
    """Write path-free selector diagnostics without changing the R1 inputs."""
    manifest_path = out / "manifest.json"
    frames_dir = out / "frames"
    try:
        with tempfile.TemporaryDirectory(prefix="astrakriti-selection-") as temporary:
            temporary = Path(temporary)
            report_path = temporary / "adaptive.json"
            adaptive = adaptive_select_frames(
                manifest_path, frames_dir, temporary / "adaptive-output",
                selection_report=str(report_path), dry_run=True,
            )
            source_rows = adaptive.get("rows")
            if not isinstance(source_rows, list):
                raise ValueError("adaptive selector returned no diagnostic rows")
            rows = []
            for row in source_rows:
                if not isinstance(row, dict):
                    continue
                rows.append({key: row.get(key) for key in (
                    "frame_number", "timestamp", "blur_score", "clipped_ratio",
                    "feature_count", "useful_match_count", "match_ratio",
                    "median_feature_displacement", "new_feature_ratio",
                    "image_similarity", "diagnostics_status", "warning",
                    "decision", "rejection_reason",
                )})
            adaptive_configuration = adaptive.get("configuration")
            config_keys = (
                "target_fps", "min_feature_displacement", "min_new_feature_ratio",
                "min_useful_matches", "min_features", "max_gap_seconds", "min_blur",
                "max_clipped_ratio", "proxy_width",
            )
            advisory = {
                "schema_version": "astrakriti3d.selection-advisory.v1",
                "status": "available" if rows and len(rows) == len(source_rows) else "partial",
                "mode": mode,
                "baseline": "R1",
                "policy": "advisory_only_all_source_frames_retained",
                "candidate_count": adaptive.get("candidate_count"),
                "recommended_count": adaptive.get("selected_count"),
                "configuration": {
                    key: adaptive_configuration.get(key)
                    for key in config_keys
                    if isinstance(adaptive_configuration, dict) and key in adaptive_configuration
                },
                "rows": rows,
                "warnings": [
                    "Experimental image proxies are not calibrated quality guarantees.",
                    "R1 remains the production baseline; every candidate frame remains in WebODM input.",
                ],
            }
            if mode == "georeferenced":
                telemetry_path = out / "telemetry" / "telemetry_ordered.json"
                if telemetry_path.is_file():
                    try:
                        coverage = coverage_aware_select_streaming(
                            manifest_path, report_path, frames_dir, telemetry_path,
                            temporary / "coverage-output",
                        )
                        advisory["coverage"] = {
                            "status": "available",
                            "candidate_count": coverage.get("candidate_count"),
                            "recommended_count": coverage.get("selected_count"),
                            "route_length_m": coverage.get("route_length_m"),
                            "configuration": coverage.get("configuration"),
                            "geo_validation": coverage.get("geo_validation"),
                            "rows": [{key: row.get(key) for key in (
                                "frame_number", "output_filename", "timestamp_seconds",
                                "gps_gap_m", "feature_redundant", "spatial_redundant",
                                "decision", "reason",
                            )} for row in coverage.get("rows", []) if isinstance(row, dict)],
                        }
                    except Exception as exc:
                        advisory["coverage"] = {
                            "status": "unavailable",
                            "detail": "Coverage diagnostics could not be measured: {}".format(type(exc).__name__),
                        }
                else:
                    advisory["coverage"] = {
                        "status": "unavailable",
                        "detail": "Ordered telemetry is unavailable; no coverage recommendation was produced.",
                    }
    except Exception as exc:
        advisory = {
            "schema_version": "astrakriti3d.selection-advisory.v1",
            "status": "unavailable",
            "mode": mode,
            "baseline": "R1",
            "policy": "advisory_only_all_source_frames_retained",
            "detail": "Experimental selection diagnostics could not be measured: {}".format(type(exc).__name__),
            "warnings": ["All source frames remain selected under the R1 production baseline."],
        }
    directory = out / "selection"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "advisory.json").write_text(json.dumps(advisory, separators=(",", ":")), encoding="utf-8")
    return advisory

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
    selection = _selection_advisory(out, selected_mode)
    final["selection"] = {
        "status": selection.get("status"),
        "policy": selection.get("policy"),
        "candidate_count": selection.get("candidate_count"),
        "recommended_count": selection.get("recommended_count"),
        "coverage_status": (selection.get("coverage") or {}).get("status"),
    }
    (out / "project_report.json").write_text(json.dumps(final, indent=2), encoding="utf-8")
    return {"mode": selected_mode, "manifest": manifest, "project_report": final}

"""Read-only production preflight for local and georeferenced inputs."""
from __future__ import annotations
import hashlib, json, os, shutil, sys
from pathlib import Path

from .config import Config
from .video import inspect_video, VideoPreparationError
from .telemetry import parse_srt, associate, TelemetryError
from .client import WebODMClient, WebODMError

MIN_FREE_DISK_BYTES = 5 * 1024**3
MIN_AVAILABLE_MEMORY_BYTES = 512 * 1024**2

def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()

def _check(name, status, message, **details):
    return {"name": name, "status": status, "message": message, **details}

def _baseline(root, validator):
    try:
        result = validator(root, root / "config" / "r1_baseline.json")
        return _check("r1_baseline", "passed" if result.get("valid") else "failed", "frozen R1 baseline is valid" if result.get("valid") else "frozen R1 baseline validation failed", details=result)
    except Exception as exc:
        return _check("r1_baseline", "failed", f"could not validate frozen R1 baseline: {exc}")

def _resource_checks(output, resource_probe, disk_probe):
    checks = []
    try:
        resources = resource_probe()
        available = int(resources["available_memory_bytes"])
        checks.append(_check("memory", "passed" if available >= MIN_AVAILABLE_MEMORY_BYTES else "failed", f"available memory {available} bytes", available_memory_bytes=available, minimum_required_bytes=MIN_AVAILABLE_MEMORY_BYTES))
    except Exception as exc:
        checks.append(_check("memory", "failed", f"memory probe failed: {exc}"))
    try:
        free = int(disk_probe(output))
        checks.append(_check("disk", "passed" if free >= MIN_FREE_DISK_BYTES else "failed", f"free disk {free} bytes", free_bytes=free, minimum_required_bytes=MIN_FREE_DISK_BYTES))
    except Exception as exc:
        checks.append(_check("disk", "failed", f"disk probe failed: {exc}"))
    return checks

def _default_resources():
    import psutil
    return {"available_memory_bytes": psutil.virtual_memory().available, "total_memory_bytes": psutil.virtual_memory().total, "cpu_count": psutil.cpu_count()}

def _default_disk(path):
    return shutil.disk_usage(Path(path).anchor or Path(path).resolve().anchor).free

def _output_check(path):
    """Validate an output path without requiring a missing directory to exist."""
    try:
        out = Path(path).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        return None, _check("output_writable", "failed", f"invalid output path: {exc}")

    if out.exists():
        if not out.is_dir():
            return out, _check("output_writable", "failed", f"output path is an existing file, not a directory: {out}", path=str(out))
        writable = os.access(out, os.W_OK)
        return out, _check(
            "output_writable", "passed" if writable else "failed",
            "output directory is writable" if writable else f"output directory is read-only or inaccessible: {out}",
            path=str(out), requested_directory_exists=True, writable=writable,
        )

    # The requested directory may be created later by the report/prepare step.
    # Check the nearest existing ancestor instead of treating a missing nested
    # directory as a permission failure.
    parent = out.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if not parent.is_dir():
        return out, _check("output_writable", "failed", f"no existing directory is available for output path: {out}", path=str(out), requested_directory_exists=False)
    writable = os.access(parent, os.W_OK)
    return out, _check(
        "output_writable", "passed" if writable else "failed",
        f"output directory will be created; nearest existing parent is writable: {parent}" if writable else f"nearest existing output parent is read-only or inaccessible: {parent}",
        path=str(out), requested_directory_exists=False, will_be_created=True,
        nearest_existing_parent=str(parent), writable=writable,
    )

def _webodm(config, client_factory):
    checks = []
    if not config.base_url:
        return [_check("webodm_api", "failed", "WEBODM_BASE_URL is not configured", action="configure WebODM credentials and URL")]
    if not config.username or not config.password:
        checks.append(_check("webodm_credentials", "failed", "WEBODM_USERNAME/WEBODM_PASSWORD is not configured", action="configure credentials"))
    try:
        client = client_factory(config)
        response = client.s.request("GET", config.base_url, timeout=config.timeout)
        if response.status_code >= 400: raise WebODMError(f"HTTP {response.status_code}")
        checks.append(_check("webodm_api", "passed", "WebODM API is reachable", url=config.base_url, http_status=response.status_code))
        client.authenticate()
        checks.append(_check("webodm_authentication", "passed", "WebODM authentication succeeded"))
        nodes_response = client.request("GET", "/processingnodes/").json()
        nodes = nodes_response if isinstance(nodes_response, list) else nodes_response.get("results", [])
        if not nodes: raise WebODMError("processing node list is empty")
        online = [n for n in nodes if n.get("online") is True or n.get("status") in ("online", 1)]
        checks.append(_check("nodeodm", "passed" if online else "failed", "at least one NodeODM is online" if online else "no online NodeODM was reported", node_count=len(nodes), online_count=len(online)))
        queues = [{k: n.get(k) for k in ("id", "hostname", "port", "queue_count", "available_options", "api_version", "engine_version", "online")} for n in nodes]
        checks.append(_check("queue_status", "passed" if all("queue_count" in n or "queue" in n for n in nodes) else "warn", "NodeODM queue status recorded", nodes=queues))
        checks.append(_check("webodm_versions", "passed", "supported options and versions recorded", nodes=queues))
    except Exception as exc:
        checks.append(_check("webodm_api", "failed", f"WebODM/NodeODM preflight failed: {exc}", action="start WebODM, authenticate, and verify NodeODM health"))
    return checks

def run_preflight(video, output, *, mode, srt=None, root=None, config=None, client_factory=WebODMClient, resource_probe=None, disk_probe=None, baseline_validator=None):
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    out, output_check = _output_check(output)
    checks = []
    if mode not in {"local", "georeferenced"}: raise ValueError("mode must be local or georeferenced")
    video = Path(video).resolve()
    checks.append(_check("video_exists", "passed" if video.is_file() else "failed", "video exists" if video.is_file() else f"video does not exist: {video}"))
    if video.is_file():
        try:
            info = inspect_video(video)
            valid = bool(info.get("codec")) and float(info.get("duration_seconds", 0)) > 0 and bool(info.get("width")) and bool(info.get("height")) and bool(info.get("avg_frame_rate"))
            checks.append(_check("video_metadata", "passed" if valid else "failed", "codec, duration, FPS, and resolution are valid" if valid else "video metadata is incomplete", codec=info.get("codec"), duration_seconds=info.get("duration_seconds"), fps=info.get("avg_frame_rate"), resolution=[info.get("width"), info.get("height")]))
        except Exception as exc:
            checks.append(_check("video_metadata", "failed", f"video inspection failed: {exc}", action="provide a readable FFmpeg-supported video"))
            info = {}
    else: info = {}
    checks.append(output_check)
    if out is not None:
        checks.extend(_resource_checks(out, resource_probe or _default_resources, disk_probe or _default_disk))
    baseline_result = (baseline_validator or __import__("scripts.validate_r1_baseline", fromlist=["validate"]).validate)
    checks.append(_baseline(root, baseline_result))
    if mode == "local":
        checks.append(_check("telemetry_policy", "passed", "local mode does not require SRT or telemetry"))
        checks.append(_check("local_reference_frame", "passed", "absolute position, CRS, GPS residuals, and geographic orientation are unavailable", crs=None, gps_residuals_available=False, geographic_orientation_available=False))
        stale = [str(p) for p in (out / "geo.txt", out / "telemetry", out / "geolocation_report.json")] if out is not None else []
        stale = [p for p in stale if Path(p).exists()]
        checks.append(_check("stale_geolocation", "failed" if stale else "passed", "no stale geo/telemetry input will be reused" if not stale else "stale geo/telemetry exists; use a fresh output directory", stale_paths=stale))
    else:
        if not srt:
            checks.append(_check("srt_exists", "failed", "georeferenced mode requires --srt PATH", action="provide the DJI SRT file"))
        else:
            srt_path = Path(srt).resolve()
            exists = srt_path.is_file()
            checks.append(_check("srt_exists", "passed" if exists else "failed", "SRT exists" if exists else f"SRT does not exist: {srt_path}"))
            if exists:
                try:
                    records, meta = parse_srt(srt_path)
                    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8")) if (out / "manifest.json").is_file() else None
                    rows, _ = associate(manifest.get("frames", []), records) if manifest else ([], [])
                    valid = bool(records) and not meta.get("errors") and not meta.get("duplicates") and not meta.get("non_monotonic") and all(r.valid for r in records)
                    checks.append(_check("srt_valid", "passed" if valid else "failed", "SRT telemetry is valid" if valid else "SRT contains malformed or invalid telemetry", sha256=_sha(srt_path), record_count=len(records), parser_errors=meta.get("errors", [])))
                    complete = bool(manifest) and len(rows) == len(manifest.get("frames", [])) and all(r.get("association_status") == "matched" for r in rows)
                    checks.append(_check("frame_associations", "passed" if complete else "failed", "all frames have complete telemetry associations" if complete else "frame-to-telemetry associations are incomplete", matched_count=sum(r.get("association_status") == "matched" for r in rows), frame_count=len(rows)))
                except Exception as exc:
                    checks.append(_check("srt_valid", "failed", f"SRT validation failed: {exc}", action="provide valid DJI telemetry"))
        stale = [str(p) for p in (out / "geo.txt", out / "telemetry", out / "geolocation_report.json")] if out is not None else []
        stale = [p for p in stale if Path(p).exists()]
        checks.append(_check("stale_geolocation", "failed" if stale else "passed", "no stale telemetry or geo.txt will be reused" if not stale else "existing geographic files require a fresh output directory", stale_paths=stale))
        checks.append(_check("geo_format", "passed", "geo.txt will use EPSG:4326 and filename longitude latitude ordering", crs="EPSG:4326", coordinate_order="filename longitude latitude", generated=False))
    checks.extend(_webodm(config or Config.from_env(), client_factory))
    critical_failed = [c for c in checks if c["status"] == "failed"]
    status = "FAIL" if critical_failed else ("WARN" if any(c["status"] == "warn" for c in checks) else "PASS")
    report = {"schema_version": "astrakriti3d.preflight.v1", "status": status, "mode": mode, "read_only": True, "video": str(video), "output": str(out), "input_hashes": {"video": _sha(video) if video.is_file() else None, "srt": _sha(Path(srt)) if srt and Path(srt).is_file() else None}, "environment": {"python": sys.version, "webodm_url": (config or Config.from_env()).base_url}, "checks": checks, "actionable_failures": [c for c in checks if c["status"] == "failed"]}
    report_dir = out if out is not None and (not out.exists() or out.is_dir()) else None
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
    if report_dir is None:
        return report
    (report_dir / "preflight.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Astrakriti3D production preflight", "", f"Status: **{status}**", f"Mode: `{mode}`", "", "| Check | Status | Message |", "|---|---|---|"]
    lines += [f"| {c['name']} | {c['status'].upper()} | {c['message']} |" for c in checks]
    if report["actionable_failures"]:
        lines += ["", "## Actionable failures", ""] + [f"- {c['message']}. {c.get('action', '')}" for c in report["actionable_failures"]]
    (report_dir / "preflight.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report

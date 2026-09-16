import hashlib, json, math, struct, zipfile, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astrakriti3d.client import WebODMClient
from astrakriti3d.config import Config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/phase16/aggressive-webodm-20260915"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def geo(path):
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        p = line.split()
        if p: rows[p[0]] = (float(p[1]), float(p[2]))
    return rows

def shots(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return {f["properties"]["filename"]: f for f in data.get("features", []) if f.get("properties", {}).get("filename")}

def residuals(expected, returned):
    values = []
    for name, (lon, lat) in expected.items():
        f = returned.get(name)
        if not f: continue
        c = f.get("geometry", {}).get("coordinates", [])
        if len(c) < 2: continue
        mid = math.radians((lat + float(c[1])) / 2)
        dx = math.radians(float(c[0]) - lon) * 6371000 * math.cos(mid)
        dy = math.radians(float(c[1]) - lat) * 6371000
        values.append(math.hypot(dx, dy))
    values.sort()
    def pct(q):
        if not values: return None
        return values[min(len(values) - 1, math.ceil(q * len(values)) - 1)]
    return {"matched_count": len(values), "mean_meters": sum(values) / len(values) if values else None, "median_meters": pct(.5), "p95_meters": pct(.95), "maximum_meters": max(values) if values else None}

def ply_info(path):
    if not path.is_file(): return None
    header = path.read_bytes()[:8192].decode("ascii", errors="ignore")
    def value(prefix):
        for line in header.splitlines():
            if line.startswith(prefix): return int(line.split()[-1])
        return None
    return {"path": str(path), "vertices": value("element vertex"), "faces": value("element face"), "size_bytes": path.stat().st_size}

def artifact(path):
    if not path.is_file(): return {"present": False}
    info = {"present": True, "size_bytes": path.stat().st_size, "sha256": sha(path)}
    if path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as z: info.update({"zip_valid": z.testzip() is None, "entry_count": len(z.infolist())})
        except Exception as e: info.update({"zip_valid": False, "error": str(e)})
    if path.suffix.lower() == ".glb": info["glb_header_valid"] = path.read_bytes()[:4] == b"glTF"
    if path.suffix.lower() == ".pdf": info["pdf_header_valid"] = path.read_bytes()[:5] == b"%PDF-"
    if path.suffix.lower() == ".tif": info["tiff_header_valid"] = path.read_bytes()[:4] in (b"II*\x00", b"MM\x00*")
    if path.suffix.lower() == ".laz": info["laz_header_valid"] = path.read_bytes()[:4] == b"LASF"
    return info

def stats(path):
    p = path / "opensfm/stats/stats.json"
    if not p.is_file(): return {}
    s = json.loads(p.read_text(encoding="utf-8"))
    r = s.get("reconstruction_statistics", {})
    return {k: r.get(k) for k in ("reconstructed_shots_count", "reconstructed_points_count", "reprojection_error_pixels", "reprojection_error_normalized", "reprojection_error_angular", "components")}

def run(name, task_id, input_geo, shots_path, artifacts, local_data, expected_count):
    c = WebODMClient(Config.from_env()); c.authenticate(); task = c.task("2", task_id)
    e = geo(input_geo); s = shots(shots_path)
    files = {k: artifact(Path(v)) for k, v in artifacts.items()}
    local_stats = stats(Path(local_data))
    return {"name": name, "task_id": task_id, "input_frame_count": expected_count, "status": task.get("status"), "processing_time_ms": task.get("processing_time"), "registered_image_count": len(s), "camera_alignment": len(s) == expected_count, "reprojection": {k: local_stats.get(k) for k in ("reprojection_error_pixels", "reprojection_error_normalized", "reprojection_error_angular")}, "point_cloud": {"count": (task.get("statistics") or {}).get("pointcloud", {}).get("points"), "density_points_per_area": ((task.get("statistics") or {}).get("pointcloud", {}).get("points") / task.get("statistics", {}).get("area")) if (task.get("statistics") or {}).get("area") else None, "area_m2": (task.get("statistics") or {}).get("area")}, "mesh": {"geometry_artifact_present": files.get("textured_model_zip", {}).get("present", False), "local_3d_mesh": ply_info(Path(local_data) / "odm_meshing/odm_mesh.ply"), "local_25d_mesh": ply_info(Path(local_data) / "odm_meshing/odm_25dmesh.ply")}, "texture": {"success": files.get("textured_model_zip", {}).get("present", False) and files.get("textured_model_zip", {}).get("zip_valid", False), "glb_valid": files.get("textured_model_glb", {}).get("glb_header_valid", False)}, "visual_quality": {"automated_rating": "not_scored", "available_textured_outputs": files.get("textured_model_zip", {}).get("present", False) and files.get("textured_model_glb", {}).get("present", False), "note": "No subjective visual score was assigned; orthophoto/model artifacts are preserved for human review."}, "coordinate_residuals_meters": residuals(e, s), "artifact_inventory": files, "warnings": [], "local_stats": local_stats}

r1 = run("R1", "ef1199ec-d6d3-4a3f-91c3-70f38f41de1c", ROOT / "evidence/phase14/controlled-20260915/R1/geo.txt", ROOT / "evidence/phase16/aggressive-webodm-20260915/baseline_artifacts/shots.geojson", {"orthophoto": ROOT / "evidence/phase16/aggressive-webodm-20260915/baseline_artifacts/orthophoto.tif", "shots": ROOT / "evidence/phase16/aggressive-webodm-20260915/baseline_artifacts/shots.geojson", "cameras": ROOT / "evidence/phase16/aggressive-webodm-20260915/baseline_artifacts/cameras.json", "report": ROOT / "evidence/phase16/aggressive-webodm-20260915/baseline_artifacts/report.pdf", "laz": ROOT / "evidence/phase16/aggressive-webodm-20260915/baseline_artifacts/georeferenced_model.laz", "textured_model_zip": ROOT / "evidence/phase16/aggressive-webodm-20260915/baseline_artifacts/textured_model.zip", "textured_model_glb": ROOT / "evidence/phase16/aggressive-webodm-20260915/baseline_artifacts/textured_model.glb"}, "C:/WebODM/resources/app/apps/NodeODX/data/e00d7c2b-3861-4a76-aa83-88c142e3baf6", 194)
ag = run("Aggressive adaptive", "63efb5b5-cd2d-44d0-a970-228d812354b0", OUT / "input/geo.txt", OUT / "artifacts/shots.geojson", {"orthophoto": OUT / "artifacts/orthophoto.tif", "shots": OUT / "artifacts/shots.geojson", "cameras": OUT / "artifacts/cameras.json", "report": OUT / "artifacts/report.pdf", "laz": OUT / "artifacts/georeferenced_model.laz", "textured_model_zip": OUT / "artifacts/textured_model.zip", "textured_model_glb": OUT / "artifacts/textured_model.glb"}, "C:/WebODM/resources/app/apps/NodeODX/data/0c4ec670-4158-4232-b097-af41810e729a", 147)
ag["visual_quality"] = {"automated_rating": "degraded_vs_R1", "human_review": "The orthophoto preview is fragmented with extensive black gaps and sparse disconnected coverage compared with the continuous R1 swath.", "preview": "aggressive_orthophoto_preview.jpg"}
r1["visual_quality"] = {"automated_rating": "baseline_reference", "human_review": "The orthophoto preview shows a continuous mapped swath with edge artifacts; used as the visual reference.", "preview": "r1_orthophoto_preview.jpg"}
ag["coverage_assessment"] = {"coordinate_residuals_are_high": ag["coordinate_residuals_meters"]["median_meters"] > 10, "note": "All cameras registered, but returned camera coordinates differ materially from this run's geo.txt; this is a coverage/georeferencing concern."}
r1["coverage_assessment"] = {"coordinate_residuals_are_high": r1["coordinate_residuals_meters"]["median_meters"] > 10, "note": "Returned camera coordinates are close to the R1 geo.txt reference."}
resource_rows = [json.loads(x) for x in (OUT / "resource_log.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
resource_summary = {"sample_count": len(resource_rows), "peak_used_ram_bytes": max((x["ram_used_bytes"] for x in resource_rows), default=None), "minimum_available_ram_bytes": min((x["ram_available_bytes"] for x in resource_rows), default=None), "minimum_free_disk_bytes": min((x["disk_free_bytes"] for x in resource_rows), default=None), "gpu_samples": sum(1 for x in resource_rows if (x.get("gpu") or {}).get("exit_code") == 0)}
report = {"schema_version": "phase16.aggressive-webodm-comparison.v1", "valid_input_preflight": json.loads((OUT / "preflight.json").read_text(encoding="utf-8"))["valid"], "webodm_options": [], "baseline": r1, "aggressive": ag, "resources": resource_summary, "comparison": {"runtime_reduction_percent": (1 - ag["processing_time_ms"] / r1["processing_time_ms"]) * 100, "registered_image_delta": ag["registered_image_count"] - r1["registered_image_count"], "point_cloud_count_delta": ag["point_cloud"]["count"] - r1["point_cloud"]["count"], "reprojection_pixels_delta": ag["reprojection"]["reprojection_error_pixels"] - r1["reprojection"]["reprojection_error_pixels"], "texture_success_equal": ag["texture"]["success"] == r1["texture"]["success"]}, "recommendation": "Keep aggressive adaptive experimental; it completed successfully with full camera alignment and valid textured artifacts, but its coordinate residuals and visual coverage are materially worse than R1."}
(OUT / "comparison_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
md = ["# R1 vs aggressive adaptive WebODM comparison", "", "## Recommendation", "", report["recommendation"], "", "| Run | Frames | Runtime (s) | Registered | Alignment | Reprojection px | Point cloud | Textured output |", "|---|---:|---:|---:|---|---:|---:|---|"]
for x in (r1, ag): md.append(f"| {x['name']} | {x['input_frame_count']} | {x['processing_time_ms']/1000:.2f} | {x['registered_image_count']} | {'success' if x['camera_alignment'] else 'failed'} | {x['reprojection']['reprojection_error_pixels']:.6f} | {x['point_cloud']['count']} | {'success' if x['texture']['success'] else 'failed'} |")
md += ["", "## Findings", "", f"- Aggressive input reduction: 194 to 147 frames ({(1-147/194)*100:.2f}% fewer).", f"- Runtime change: {report['comparison']['runtime_reduction_percent']:.2f}%.", "- Both runs registered every input image and produced valid textured artifacts.", f"- Point-cloud count: aggressive {ag['point_cloud']['count']:,} vs R1 {r1['point_cloud']['count']:,}.", f"- Reprojection error increased from {r1['reprojection']['reprojection_error_pixels']:.6f}px to {ag['reprojection']['reprojection_error_pixels']:.6f}px.", f"- Coordinate residuals: aggressive median {ag['coordinate_residuals_meters']['median_meters']:.2f}m / P95 {ag['coordinate_residuals_meters']['p95_meters']:.2f}m versus R1 median {r1['coordinate_residuals_meters']['median_meters']:.2f}m / P95 {r1['coordinate_residuals_meters']['p95_meters']:.2f}m.", "- Visual inspection found substantially more fragmented aggressive coverage and large black gaps; it is not visually equivalent to R1.", "- Meshes and textures completed structurally, but that does not establish coverage or visual-quality parity.", "- Artifact hashes are in comparison_report.json and artifact_inventory.json.", "", "## Evidence", "", "- Input preflight: `preflight.json`", "- Submission/task: `submission.json`, `task_final.json`", "- Status/resource logs: `status_events.jsonl`, `resource_log.jsonl`", "- Engine log: `webodm-output-final.log`", "- Baseline artifacts: `baseline_artifacts/`", "- Aggressive artifacts: `artifacts/`", "- Visual previews: `r1_orthophoto_preview.jpg`, `aggressive_orthophoto_preview.jpg`", "", "Final recommendation: R2/R3/aggressive adaptive remains experimental; do not promote because coverage/georeferencing and visual quality are materially worse than R1."]
md += [f"- Resource samples: {resource_summary['sample_count']}; minimum available RAM {resource_summary['minimum_available_ram_bytes'] / 1e9:.2f} GB; minimum free disk {resource_summary['minimum_free_disk_bytes'] / 1e9:.2f} GB; GPU samples {resource_summary['gpu_samples']}.", "", "## Evidence", "", "- Input preflight: `preflight.json`", "- Submission/task: `submission.json`, `task_final.json`", "- Status/resource logs: `status_events.jsonl`, `resource_log.jsonl`", "- Engine log: `webodm-output-final.log`", "- Baseline artifacts: `baseline_artifacts/`", "- Aggressive artifacts: `artifacts/`", "- Visual previews: `r1_orthophoto_preview.jpg`, `aggressive_orthophoto_preview.jpg`", "", "Final recommendation: R2/R3/aggressive adaptive remains experimental; do not promote because coverage/georeferencing and visual quality are materially worse than R1."]
(OUT / "comparison_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print(json.dumps({"r1": {"registered": r1["registered_image_count"], "runtime_ms": r1["processing_time_ms"], "points": r1["point_cloud"]["count"]}, "aggressive": {"registered": ag["registered_image_count"], "runtime_ms": ag["processing_time_ms"], "points": ag["point_cloud"]["count"]}}, indent=2))

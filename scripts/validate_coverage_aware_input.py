import hashlib, json, statistics
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/phase18/coverage-aware-20260915-v14"
manifest = json.loads((OUT / "selection_manifest.json").read_text(encoding="utf-8"))
selected = manifest["selected"]
rows = manifest["rows"]
images = sorted((OUT / "frames").glob("*.jpg"), key=lambda p: p.name)
geo_lines = [x.split() for x in (OUT / "geo.txt").read_text(encoding="utf-8").splitlines() if x.strip()]
geo = {x[0]: (float(x[1]), float(x[2])) for x in geo_lines[1:]}
issues = []
if len(images) != len(selected): issues.append(f"image count {len(images)} != selected count {len(selected)}")
if len(geo) != len(selected): issues.append(f"geo count {len(geo)} != selected count {len(selected)}")
if set(geo) != {x["output_filename"] for x in selected}: issues.append("geo names do not exactly match selected names")
if [x["output_filename"] for x in selected] != sorted(x["output_filename"] for x in selected): issues.append("selected manifest is not filename ordered")
if any(selected[i]["source_timestamp_seconds"] > selected[i + 1]["source_timestamp_seconds"] for i in range(len(selected) - 1)): issues.append("selected timestamps are not chronological")
for p in images:
    with Image.open(p) as im:
        if im.size != (5472, 3078): issues.append(f"unexpected dimensions: {p.name} {im.size}")
    expected = next(x["sha256"] for x in selected if x["output_filename"] == p.name)
    if expected != hashlib.sha256(p.read_bytes()).hexdigest(): issues.append(f"hash mismatch: {p.name}")
gaps_t = [float(b["source_timestamp_seconds"]) - float(a["source_timestamp_seconds"]) for a, b in zip(selected, selected[1:])]
gaps_g = [(((float(b["longitude"]) - float(a["longitude"])) ** 2 + (float(b["latitude"]) - float(a["latitude"])) ** 2) ** 0.5) * 111320 for a, b in zip(selected, selected[1:])]
route = [float(x["cumulative_route_m"]) for x in rows if x["decision"] == "keep"]
reasons = {}
for row in rows:
    if row["decision"] == "reject": reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
result = {
    "schema_version": "coverage-aware-input-preflight.v1",
    "candidate_count": manifest["candidate_count"], "selected_count": manifest["selected_count"], "rejected_count": manifest["rejected_count"],
    "temporal_gaps_seconds": {"min": min(gaps_t), "median": statistics.median(gaps_t), "p95": sorted(gaps_t)[int(.95 * len(gaps_t))], "max": max(gaps_t)},
    "gps_gaps_m_approx": {"min": min(gaps_g), "median": statistics.median(gaps_g), "p95": sorted(gaps_g)[int(.95 * len(gaps_g))], "max": max(gaps_g)},
    "route_coverage": {"total_route_m": manifest["route_length_m"], "selected_route_start_m": min(route), "selected_route_end_m": max(route), "coverage_fraction": (max(route) - min(route)) / manifest["route_length_m"], "max_temporal_gap_seconds": manifest["configuration"]["max_temporal_gap_seconds"], "max_spatial_gap_m": manifest["configuration"]["max_spatial_gap_m"]},
    "geo_txt": {"header": geo_lines[0][0], "record_count": len(geo), "unique": len(geo) == len(geo_lines) - 1, "names_match": set(geo) == {x["output_filename"] for x in selected}, "sha256": hashlib.sha256((OUT / "geo.txt").read_bytes()).hexdigest()},
    "filenames": {"count": len(images), "unique": len({p.name for p in images}) == len(images), "ordered": [p.name for p in images] == sorted(p.name for p in images), "first": images[0].name, "last": images[-1].name},
    "rejected_frame_reasons": reasons, "issues": issues, "valid": not issues and 220 <= len(selected) <= 280,
    "r1_baseline_task": "ef1199ec-d6d3-4a3f-91c3-70f38f41de1c", "webodm_options": [],
}
(OUT / "validation_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
md = "# Coverage-aware selection validation\n\n"
md += f"- Candidate frames: {result['candidate_count']}\n- Selected frames: {result['selected_count']}\n- Rejected frames: {result['rejected_count']}\n- Route length: {result['route_coverage']['total_route_m']:.2f} m\n- Route coverage fraction: {result['route_coverage']['coverage_fraction']:.3f}\n- Temporal gap max: {result['temporal_gaps_seconds']['max']:.3f} s\n- Approximate GPS gap max: {result['gps_gaps_m_approx']['max']:.3f} m\n- Geo records: {result['geo_txt']['record_count']}\n- Validation: {'PASS' if result['valid'] else 'FAIL'}\n\n## Rejected-frame reasons\n\n"
for k, v in reasons.items(): md += f"- {k}: {v}\n"
md += "\nThe selector rejects a frame only when feature redundancy and spatial redundancy are both confirmed. Endpoints, turns, time windows, route segments, and continuity are protected.\n"
(OUT / "validation_report.md").write_text(md, encoding="utf-8")
print(json.dumps(result, indent=2))
raise SystemExit(0 if result["valid"] else 4)

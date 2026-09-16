import hashlib, json, math
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/phase16/aggressive-webodm-20260915"
inp = OUT / "input"
images = sorted((inp / "images").glob("*.jpg"), key=lambda p: p.name)
selection = json.loads((inp / "selection.json").read_text(encoding="utf-8"))
candidate = json.loads((inp / "candidate_manifest.json").read_text(encoding="utf-8"))
telemetry = json.loads((ROOT / "evidence/phase3/real-run/telemetry_ordered.json").read_text(encoding="utf-8"))
geo_lines = [x.split() for x in (inp / "geo.txt").read_text(encoding="utf-8").splitlines() if x.strip()]
geo = {x[0]: (float(x[1]), float(x[2])) for x in geo_lines[1:]}
selected = selection["frames"]
candidate_by_name = {x["output_filename"]: x for x in candidate["frames"]}
issues = []
dimensions = []
hash_checks = []
for idx, path in enumerate(images):
    if idx >= len(selected) or path.name != selected[idx]["output_filename"]:
        issues.append({"type": "ordering", "filename": path.name, "index": idx})
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = selected[idx]["sha256"] if idx < len(selected) else None
    hash_checks.append(digest == expected)
    if digest != expected:
        issues.append({"type": "selection_hash", "filename": path.name})
    with Image.open(path) as image:
        dimensions.append(list(image.size))
    if path.name not in candidate_by_name:
        issues.append({"type": "candidate_manifest", "filename": path.name})

telemetry_matches = []
for item in selected:
    c = candidate_by_name.get(item["output_filename"])
    if c is None:
        continue
    timestamp = float(c["source_timestamp_seconds"])
    nearest = min(telemetry, key=lambda row: abs(float(row["cue_start_seconds"]) - timestamp))
    delta = abs(float(nearest["cue_start_seconds"]) - timestamp)
    lat, lon = geo.get(item["output_filename"], (None, None))
    ok = bool(nearest.get("valid")) and delta <= 0.05 and lat is not None and lon is not None
    telemetry_matches.append({
        "filename": item["output_filename"],
        "source_timestamp_seconds": timestamp,
        "telemetry_record_id": nearest["record_id"],
        "telemetry_timestamp_seconds": nearest["cue_start_seconds"],
        "absolute_time_delta_seconds": delta,
        "coordinates_present": lat is not None and lon is not None,
        "coordinate_match": lat is not None and abs(lat - float(nearest["longitude"])) < 1e-9 and abs(lon - float(nearest["latitude"])) < 1e-9,
        "valid": ok,
    })
result = {
    "schema_version": "phase16.aggressive-webodm-preflight.v1",
    "image_count": len(images),
    "selection_count": selection.get("selected_count"),
    "geo_record_count": len(geo_lines) - 1,
    "geo_unique_count": len(geo),
    "ordered_unique_filenames": len({p.name for p in images}) == len(images) and [p.name for p in images] == sorted({p.name for p in images}),
    "geo_names_match_images": set(geo) == {p.name for p in images},
    "selection_names_match_images": [p.name for p in images] == [x["output_filename"] for x in selected],
    "selection_hashes_match": all(hash_checks) and len(hash_checks) == len(images),
    "dimensions": sorted({tuple(x) for x in dimensions}),
    "telemetry_association_count": sum(x["valid"] for x in telemetry_matches),
    "telemetry_associations_complete": len(telemetry_matches) == len(images) and all(x["valid"] for x in telemetry_matches),
    "telemetry_max_absolute_time_delta_seconds": max((x["absolute_time_delta_seconds"] for x in telemetry_matches), default=None),
    "telemetry_coordinate_matches": sum(x["coordinate_match"] for x in telemetry_matches),
    "issues": issues,
    "valid": len(images) == 147 and selection.get("selected_count") == 147 and len(geo_lines) - 1 == 147 and not issues and len(telemetry_matches) == 147 and all(x["valid"] for x in telemetry_matches),
    "source": {
        "selection": str((inp / "selection.json").resolve()),
        "candidate_manifest": str((inp / "candidate_manifest.json").resolve()),
        "telemetry": str((ROOT / "evidence/phase3/real-run/telemetry_ordered.json").resolve()),
        "geo": str((inp / "geo.txt").resolve()),
    },
}
(OUT / "preflight.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
raise SystemExit(0 if result["valid"] else 4)

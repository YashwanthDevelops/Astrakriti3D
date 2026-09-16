"""Validate that the frozen R1 inputs and configuration remain unchanged."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

REQUIRED_ASSOCIATION_FIELDS = {
    "frame_filename", "frame_timestamp_seconds", "matched_telemetry_timestamp_seconds",
    "latitude", "longitude", "altitude", "telemetry_record_id"
}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def fail(issues, message):
    issues.append(message)

def validate(root: Path, spec_path: Path) -> dict:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    issues = []
    def path(key):
        return root / key
    source = spec["source"]
    video = path(source["video"])
    if not video.is_file(): fail(issues, f"missing source video: {video}")
    elif sha256(video) != source["video_sha256"]: fail(issues, "source video SHA-256 changed")
    extraction = spec["extraction"]
    manifest_path = path(extraction["manifest"])
    frame_dir = path(extraction["frame_directory"])
    if not manifest_path.is_file():
        fail(issues, f"missing manifest: {manifest_path}"); manifest = {}
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if sha256(manifest_path) != extraction["manifest_sha256"]: fail(issues, "R1 manifest SHA-256 changed")
    if manifest:
        video_info = manifest.get("video", {})
        if abs(float(video_info.get("duration_seconds", -1)) - source["duration_seconds"]) > source["duration_tolerance_seconds"]: fail(issues, "video duration changed")
        sampling = manifest.get("sampling", {})
        if sampling.get("interval_seconds") != extraction["interval_seconds"]: fail(issues, "manifest interval_seconds changed")
        # The preserved phase2 manifest predates the explicit extraction_mode
        # field. Its per-frame transformation records are the frozen evidence
        # for seek mode and remain part of the compatibility contract.
        if sampling.get("extraction_mode") not in (None, extraction["extraction_mode"]): fail(issues, "manifest extraction_mode changed")
        frames = manifest.get("frames", [])
        if len(frames) != extraction["expected_frame_count"]: fail(issues, f"frame count {len(frames)} != {extraction['expected_frame_count']}")
        names = [f.get("output_filename") for f in frames]
        expected_names = [f"frame_{i:06d}.jpg" for i in range(1, extraction["expected_frame_count"] + 1)]
        if names != expected_names: fail(issues, "filenames are not unique, ordered, and contiguous")
        timestamps = [f.get("source_timestamp_seconds") for f in frames]
        if any(not isinstance(t, (int, float)) or t < 0 for t in timestamps) or timestamps != sorted(timestamps): fail(issues, "timestamps are invalid or unordered")
        if any(f.get("dimensions") != {"width": spec["images"]["width"], "height": spec["images"]["height"]} for f in frames): fail(issues, "image dimensions differ from R1")
        if any(not f.get("sha256") for f in frames): fail(issues, "manifest is missing source-frame hashes")
        if any("seek" not in f.get("transformations", {}).get("extraction", "") for f in frames): fail(issues, "R1 frame extraction provenance is not seek mode")
        for frame in frames:
            image = frame_dir / frame["output_filename"]
            if not image.is_file(): fail(issues, f"missing R1 image: {image.name}")
            elif sha256(image) != frame["sha256"]: fail(issues, f"image hash mismatch: {image.name}")
    association_path = path(spec["telemetry"]["association_manifest"])
    if not association_path.is_file():
        fail(issues, f"missing association manifest: {association_path}")
    else:
        if sha256(association_path) != spec["telemetry"]["association_manifest_sha256"]: fail(issues, "telemetry association SHA-256 changed")
        rows = json.loads(association_path.read_text(encoding="utf-8")).get("rows", [])
        names = [r.get("frame_filename") for r in rows]
        expected = [f"frame_{i:06d}.jpg" for i in range(1, extraction["expected_frame_count"] + 1)]
        if names != expected: fail(issues, "telemetry rows do not exactly cover ordered R1 frames")
        for row in rows:
            if set(row) < REQUIRED_ASSOCIATION_FIELDS or row.get("association_status") != spec["telemetry"]["required_status"]: fail(issues, f"incomplete telemetry association: {row.get('frame_filename')}")
    geo_path = path(spec["geo"]["file"])
    if not geo_path.is_file():
        fail(issues, f"missing geo.txt: {geo_path}")
    else:
        if sha256(geo_path) != spec["geo"]["sha256"]: fail(issues, "R1 geo.txt SHA-256 changed")
        lines = [line.strip() for line in geo_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines or lines[0] != spec["geo"]["crs"]: fail(issues, "geo.txt CRS header changed")
        records = [line.split() for line in lines[1:]]
        names = [r[0] for r in records if len(r) == 3]
        if len(records) != spec["geo"]["expected_record_count"] or names != [f"frame_{i:06d}.jpg" for i in range(1, extraction["expected_frame_count"] + 1)]: fail(issues, "geo.txt records are incomplete or unordered")
        try:
            for record in records:
                float(record[1]); float(record[2])
        except (IndexError, ValueError): fail(issues, "geo.txt coordinates are invalid")
    return {"valid": not issues, "issues": issues, "spec": str(spec_path), "checked_frame_count": extraction["expected_frame_count"]}

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--spec", type=Path, default=None)
    args = parser.parse_args(argv)
    spec = args.spec or args.root / "config" / "r1_baseline.json"
    result = validate(args.root.resolve(), spec.resolve())
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1

if __name__ == "__main__":
    sys.exit(main())

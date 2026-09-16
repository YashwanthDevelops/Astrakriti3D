"""Read-only validation and failure classification for frame experiments."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def _image_info(path):
    from PIL import Image
    p = Path(path)
    info = {"name": p.name, "path": str(p.resolve()), "sha256": _sha(p), "bytes": p.stat().st_size}
    with Image.open(p) as im:
        im.verify()
    with Image.open(p) as im:
        im.load()  # verify() alone does not decode JPEG pixel data.
        exif=im.getexif()
        info.update({"dimensions": list(im.size), "mode": im.mode,
                     "orientation": int(exif.get(274, 1)),
                     "format": im.format, "has_exif_gps": 34853 in exif})
    return info

def validate_selection(images_dir, geo_txt, selection_manifest=None):
    """Validate selected images and exact geo.txt membership without mutation."""
    image_dir = Path(images_dir)
    files = sorted(p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png','.tif','.tiff'})
    images, errors = [], []
    for p in files:
        try: images.append(_image_info(p))
        except Exception as exc: errors.append({"file": p.name, "error": str(exc), "kind": "unreadable_image"})
    dims = {tuple(x["dimensions"]) for x in images if "dimensions" in x}
    orientations = {x.get("orientation") for x in images if "orientation" in x}
    modes = {x.get("mode") for x in images if "mode" in x}
    gps_flags = {x.get("has_exif_gps") for x in images if "has_exif_gps" in x}
    hashes = [x["sha256"] for x in images]
    duplicates = sorted({h for h in hashes if hashes.count(h) > 1})
    if not files: errors.append({"kind": "empty_selection"})
    for kind, values in (("dimensions", dims), ("orientation", orientations),
                         ("mode", modes), ("exif_gps_presence", gps_flags)):
        if len(values) > 1: errors.append({"kind": "inconsistent_" + kind})
    if any(x not in range(1, 9) for x in orientations):
        errors.append({"kind": "invalid_orientation"})
    if duplicates: errors.append({"kind": "duplicate_image_content", "sha256": duplicates})
    lines = Path(geo_txt).read_text(encoding='utf-8').splitlines()
    if not lines or lines[0] != 'EPSG:4326': errors.append({"kind":"geo_header", "error":"geo.txt must begin with EPSG:4326"})
    geo_names=[]
    for line in lines[1:]:
        parts=line.split()
        if len(parts) != 3: errors.append({"kind":"geo_record", "error":f"invalid record: {line}"}); continue
        geo_names.append(parts[0])
        try:
            lon,lat=float(parts[1]),float(parts[2])
            if not (-180 <= lon <= 180 and -90 <= lat <= 90): raise ValueError('coordinate out of range')
        except Exception as exc: errors.append({"kind":"invalid_coordinate", "file":parts[0], "error":str(exc)})
    names={x["name"] for x in images}
    if set(geo_names) != names or len(geo_names) != len(names):
        errors.append({"kind":"geo_image_membership", "missing":sorted(names-set(geo_names)), "extra":sorted(set(geo_names)-names), "duplicate_records":len(geo_names)-len(set(geo_names))})
    manifest_match=None
    if selection_manifest:
        m=json.loads(Path(selection_manifest).read_text(encoding='utf-8'))
        expected={x.get('output_filename'):x.get('source_sha256') for x in m.get('frames',[])}
        actual={x['name']:x['sha256'] for x in images}
        manifest_match=(len(expected)==len(m.get('frames',[])) and
                        all(actual.get(k)==v for k,v in expected.items()) and set(actual)==set(expected))
        if not manifest_match: errors.append({"kind":"selection_manifest_hash_mismatch"})
    return {"schema_version":"phase6.selection_preflight.v1", "image_count":len(images), "images":images,
            "uniform_dimensions":len(dims)==1, "dimensions":sorted([list(x) for x in dims]),
            "uniform_orientation":len(orientations)<=1, "orientations":sorted(orientations),
            "uniform_mode":len(modes)<=1, "modes":sorted(modes), "uniform_exif_gps_presence":len(gps_flags)<=1,
            "exif_gps_presence":sorted(gps_flags), "duplicate_content_sha256":duplicates,
            "geo_txt":str(Path(geo_txt).resolve()), "geo_record_count":len(geo_names),
            "geo_names_match_images":set(geo_names)==names and len(geo_names)==len(names),
            "selection_manifest_match":manifest_match, "errors":errors, "valid":not errors}

def classify_failure(log_path, task=None, artifacts=None):
    text=Path(log_path).read_text(encoding='utf-8', errors='replace') if log_path and Path(log_path).is_file() else ''
    components=re.search(r'(\d+) partial reconstructions in total',text)
    component_count=int(components.group(1)) if components else None
    if 'cv2.error: Unknown C++ exception' in text and 'cv2.getNumThreads()' in text:
        kind='opencv_thread_runtime_exception'
    elif any(s in text.lower() for s in ('out of memory', 'bad_alloc', 'cannot allocate memory')): kind='resource_memory_failure'
    elif 'no space left on device' in text.lower(): kind='resource_disk_failure'
    elif 'cv2.error: Unknown C++ exception' in text and 'undistort' in text.lower(): kind='opencv_undistortion_exception'
    elif component_count is not None and component_count>1: kind='fragmented_reconstruction'
    else: kind='engine_failure'
    return {"schema_version":"phase6.failure.v1", "classification":kind,
            "partial_reconstruction":'partial reconstructions' in text,
            "reconstruction_component_count":component_count,
            "fragmented_reconstruction":component_count>1 if component_count is not None else None,
            "negative_gsd_warning":'Negative GSDs detected' in text,
            "task_status":(task or {}).get('status'), "task_error":(task or {}).get('last_error'),
            "artifacts_present":bool(artifacts), "log_sha256":_sha(log_path) if log_path and Path(log_path).is_file() else None,
            "failure_site":"cv2.getNumThreads before image dispatch" if kind=='opencv_thread_runtime_exception' else None,
            "root_cause_confirmed":False}

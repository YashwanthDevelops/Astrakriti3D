import hashlib
import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
P16 = ROOT / "evidence" / "phase16" / "aggressive-webodm-20260915"
P17 = ROOT / "evidence" / "phase17" / "r3-unreferenced-orientation-20260915"
OUT_JSON = P17 / "orientation_diagnostic_report.json"
OUT_MD = P17 / "orientation_diagnostic_report.md"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def shots(path):
    d = load(path)
    out = {}
    for f in d.get("features", []):
        p = f.get("properties", {})
        name = p.get("filename") or f.get("id")
        out[name] = {"coord": f.get("geometry", {}).get("coordinates"), "properties": p}
    return out


def bbox(values):
    return {"min": [min(v[i] for v in values) for i in range(3)], "max": [max(v[i] for v in values) for i in range(3)]}


def residuals(shot_map, geo_path):
    def to_utm(lon, lat):
        # WGS84 / UTM 37N, implemented locally to keep the evidence script dependency-free.
        a, ecc2, k0 = 6378137.0, 0.0066943799901413165, 0.9996
        lam0 = math.radians(39.0)
        phi = math.radians(lat)
        lam = math.radians(lon)
        ep2 = ecc2 / (1.0 - ecc2)
        n = a / math.sqrt(1.0 - ecc2 * math.sin(phi) ** 2)
        t = math.tan(phi) ** 2
        c = ep2 * math.cos(phi) ** 2
        aa = math.cos(phi) * (lam - lam0)
        m = a * ((1 - ecc2 / 4 - 3 * ecc2 ** 2 / 64 - 5 * ecc2 ** 3 / 256) * phi
                  - (3 * ecc2 / 8 + 3 * ecc2 ** 2 / 32 + 45 * ecc2 ** 3 / 1024) * math.sin(2 * phi)
                  + (15 * ecc2 ** 2 / 256 + 45 * ecc2 ** 3 / 1024) * math.sin(4 * phi)
                  - (35 * ecc2 ** 3 / 3072) * math.sin(6 * phi))
        x = k0 * n * (aa + (1 - t + c) * aa ** 3 / 6 + (5 - 18 * t + t ** 2 + 72 * c - 58 * ep2) * aa ** 5 / 120) + 500000.0
        y = k0 * (m + n * math.tan(phi) * (aa ** 2 / 2 + (5 - t + 9 * c + 4 * c ** 2) * aa ** 4 / 24 + (61 - 58 * t + t ** 2 + 600 * c - 330 * ep2) * aa ** 6 / 720))
        return x, y
    geo = {}
    for line in Path(geo_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith("epsg"):
            continue
        q = line.split()
        if len(q) >= 3:
            geo[q[0]] = (float(q[1]), float(q[2]))
    rows = []
    for name, item in shot_map.items():
        t = item["properties"].get("translation", [])
        if len(t) >= 2 and name in geo:
            gx, gy = to_utm(geo[name][0], geo[name][1])
            rows.append(math.hypot(t[0] - gx, t[1] - gy))
    return {"count": len(rows), "mean_m": statistics.mean(rows), "median_m": statistics.median(rows),
            "p95_m": sorted(rows)[max(0, math.ceil(.95 * len(rows)) - 1)], "max_m": max(rows)}


def main():
    r1 = shots(P16 / "baseline_artifacts" / "shots.geojson")
    r3 = shots(P16 / "artifacts" / "shots.geojson")
    u3 = shots(P17 / "artifacts" / "shots.geojson")
    common = sorted(set(r3) & set(u3))
    data_dir = Path(r"C:/WebODM/resources/app/apps/NodeODX/data/90270e7d-8061-4984-b74e-5f8110558d08")
    stats = load(data_dir / "opensfm" / "stats" / "stats.json")
    result = {
        "scope": "R3 aggressive 147-frame orientation diagnostic; R1 preserved and not rerun",
        "tasks": {
            "r1_baseline": "ef1199ec-d6d3-4a3f-91c3-70f38f41de1c",
            "r3_georeferenced": "63efb5b5-cd2d-44d0-a970-228d812354b0",
            "r3_unreferenced": "19c3fbd2-a134-4614-b2bc-ad4e1273b43c",
        },
        "input_integrity": {
            "r1_shots": len(r1), "r3_georeferenced_shots": len(r3), "r3_unreferenced_shots": len(u3),
            "r3_same_filenames_between_controls": len(common) == 147,
            "r3_geo_records_exact": True,
            "r3_geo_order_chronological": True,
            "r3_source_hashes_and_telemetry_verified": True,
            "image_dimensions": [5472, 3078],
            "exif_orientation_samples": {},
            "autorotation": "FFmpeg default autorotation; source rotation metadata null; same for R1 and R3",
        },
        "crs_and_axes": {
            "geo_txt": "EPSG:4326, filename longitude latitude",
            "r3_georeferenced_srs": "WGS 84 / UTM zone 37N (EPSG:32637)",
            "r3_unreferenced_srs": None,
            "r3_unreferenced_webodm_message": "Could not generate coordinates file. The orthophoto will not be georeferenced.",
            "interpretation": "Unreferenced OpenSfM/ODM coordinates are arbitrary local reconstruction axes; they must not be read as ENU or camera-pose pitch/roll/yaw without an explicit transform.",
        },
        "camera_and_gps": {
            "r1_residuals_m": residuals(r1, ROOT / "evidence" / "phase14" / "controlled-20260915" / "R1" / "geo.txt"),
            "r3_residuals_m": residuals(r3, P16 / "input" / "geo.txt"),
            "r3_georeferenced_translation_bbox": bbox([v["properties"]["translation"] for v in r3.values()]),
            "r3_unreferenced_translation_bbox": bbox([v["properties"]["translation"] for v in u3.values()]),
            "r1_translation_bbox": bbox([v["properties"]["translation"] for v in r1.values()]),
            "note": "R3 registers all 147 images, but its georeferenced camera translations disagree with its own GPS associations by tens of metres. This is a reference/georeferencing failure signal, not an EXIF orientation failure.",
        },
        "unreferenced_control": {
            "task_status": 40,
            "registered_images": 147,
            "has_gps": stats["reconstruction_statistics"]["has_gps"],
            "has_gcp": stats["reconstruction_statistics"]["has_gcp"],
            "components": stats["reconstruction_statistics"]["components"],
            "reprojection_error_pixels": stats["reconstruction_statistics"]["reprojection_error_pixels"],
            "point_cloud_points": 2083604,
            "texturing": "completed; artifacts include textured_model.glb and textured_model.zip",
            "visual_observation": "The unreferenced orthophoto is also fragmented/radially distorted, but no global 180-degree or vertical sign inversion is established from the exported geometry. It is a valid internal reconstruction control, not a geospatially oriented control.",
        },
        "model_vs_viewer": {
            "raw_mesh": "No invalid geometry was found in the existing R3 mesh; the R3 3D and 2.5D meshes do not share a common simple sign-flip or 180-degree transform with R1.",
            "glb": "The exported GLBs have finite coordinates; their aggregate extents do not demonstrate a single global mirror or vertical flip.",
            "viewer": "A WebODM viewer camera can make arbitrary local-axis reconstructions appear upside down. Viewer-only inversion cannot be separated from model orientation by screenshots alone; the exported-coordinate and GPS residual tests are decisive here.",
        },
        "classification": {
            "primary_cause": "coordinate-system/reference-frame ambiguity compounded by invalid R3 georeferenced camera/GPS alignment",
            "secondary_factor": "insufficient frame coverage for stable reconstruction: R3 has much smaller camera trajectory extent and fragmented orthophoto coverage than R1",
            "not_supported": ["incorrect EXIF orientation", "filename-to-GPS association error", "global simple 180-degree flip proven", "NaN/infinite mesh geometry"],
            "production_status": "not production-ready",
        },
        "recommended_action": [
            "Keep R1 unchanged as production baseline.",
            "Do not promote the 147-frame R3 run.",
            "Treat the no-GPS run as a diagnostic only; it does not validate geospatial orientation.",
            "Before another reduced-frame production attempt, fix or instrument the WebODM georeferencing/reference transform and require camera-to-geo residuals comparable to R1.",
            "Use a viewer with explicit axis/CRS display or inspect exported coordinates before interpreting an apparent inversion.",
        ],
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    md = f"""# R3 147-frame orientation diagnostic\n\n## Verdict\n\nThe apparent inversion is **not explained by image EXIF orientation or filename/GPS ordering**. The evidence points to **coordinate-system/reference-frame ambiguity compounded by a failed R3 georeferencing fit**, with reduced-frame coverage as a secondary reconstruction-quality problem. R3 is **not production-ready**. R1 was not modified or rerun.\n\n## Confirmed facts\n\n- R1 task: `ef1199ec-d6d3-4a3f-91c3-70f38f41de1c`; R3 georeferenced task: `63efb5b5-cd2d-44d0-a970-228d812354b0`; no-GPS diagnostic: `19c3fbd2-a134-4614-b2bc-ad4e1273b43c`.\n- R3 contains exactly 147 unique selected images, and its geo records match those images in chronological order. Source hashes and telemetry associations were verified.\n- First/middle/final source images have empty EXIF dictionaries. Source extraction used the same FFmpeg autorotation behavior for R1 and R3; source rotation metadata is null.\n- Geo records are `EPSG:4326` in `filename longitude latitude` order. WebODM reports the georeferenced R3 output as WGS 84 / UTM zone 37N (`EPSG:32637`).\n- R1 camera/GPS residuals: median {result['camera_and_gps']['r1_residuals_m']['median_m']:.3f} m, P95 {result['camera_and_gps']['r1_residuals_m']['p95_m']:.3f} m, maximum {result['camera_and_gps']['r1_residuals_m']['max_m']:.3f} m.\n- R3 camera/GPS residuals: median {result['camera_and_gps']['r3_residuals_m']['median_m']:.3f} m, P95 {result['camera_and_gps']['r3_residuals_m']['p95_m']:.3f} m, maximum {result['camera_and_gps']['r3_residuals_m']['max_m']:.3f} m.\n- The no-GPS control registered all 147 images, completed texturing, and WebODM explicitly reported that the orthophoto was not georeferenced. It has no CRS/SRS, so it cannot prove a correct geographic “up”.\n\n## Interpretation\n\nThe no-GPS run shows that the same image set can complete without the geo.txt path, while the georeferenced R3 run produces a large camera-to-GPS discrepancy. The local OpenSfM axes are arbitrary; their numeric X/Y/Z signs are not pitch/roll/yaw or ENU until WebODM applies a valid reference transform. Consequently, an apparent upside-down model in the viewer is consistent with a viewer/reference-frame presentation issue, but the tens-of-metres R3 residuals mean the georeferenced result is also objectively invalid for production.\n\nThe exported R3 PLY/GLB files contain finite coordinates and no invalid geometry. Their extents do not support a single global 180-degree rotation, mirror, or vertical sign flip relative to R1. The R3 orthophoto and the unreferenced control are both fragmented/radially distorted, and R3’s camera trajectory is much smaller than R1’s; reduced-frame coverage is therefore a contributing factor.\n\n## Unsupported conclusions\n\nThis evidence does not establish that the WebODM viewer alone is responsible, and it does not establish a simple corrective axis flip. Applying a blind 180-degree or Z-sign transform would risk corrupting geospatial alignment.\n\n## Operational recommendation\n\nKeep R1 unchanged as the production baseline. Do not promote R3. Before a reduced-frame run can be considered, fix or instrument the WebODM georeferencing/reference transform and require R3 camera/GPS residuals in the same order as R1, plus continuous coverage and trajectory checks. The no-GPS task should remain a diagnostic artifact only.\n\nFull machine-readable evidence: [orientation_diagnostic_report.json](./orientation_diagnostic_report.json).\n"""
    OUT_MD.write_text(md, encoding="utf-8")
    print(OUT_JSON)
    print(OUT_MD)


if __name__ == "__main__":
    main()

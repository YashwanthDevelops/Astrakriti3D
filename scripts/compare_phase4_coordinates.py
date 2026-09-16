"""Compare expected coordinates from geo.txt against returned camera coordinates in shots.geojson."""
import argparse, json, math, sys
from pathlib import Path

def parse_geo_txt(path):
    lines = [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines or lines[0] != "EPSG:4326":
        raise ValueError(f"geo.txt must start with EPSG:4326, got: {lines[0] if lines else 'empty'}")
    coords = {}
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 3:
            coords[parts[0]] = {
                "longitude": float(parts[1]),
                "latitude": float(parts[2]),
                "altitude": float(parts[3]) if len(parts) > 3 else None
            }
    return coords

def parse_shots_geojson(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    features = data.get("features", [])
    coords = {}
    for feat in features:
        props = feat.get("properties", {})
        fname = props.get("filename")
        geom = feat.get("geometry", {})
        c = geom.get("coordinates", [])
        if fname and len(c) >= 2:
            coords[fname] = {
                "longitude": float(c[0]),
                "latitude": float(c[1]),
                "altitude": float(c[2]) if len(c) > 2 else None,
                "translation": props.get("translation"),
                "rotation": props.get("rotation")
            }
    return coords

def compute_distance_meters(lon1, lat1, lon2, lat2):
    # Equirectangular approximation for small geographic distances
    lat_mid = math.radians((lat1 + lat2) / 2.0)
    d_lat = math.radians(lat2 - lat1) * 6371000.0
    d_lon = math.radians(lon2 - lon1) * 6371000.0 * math.cos(lat_mid)
    return math.sqrt(d_lat**2 + d_lon**2)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--geo-txt", default="evidence/phase4/real-run/geo.txt")
    p.add_argument("--shots", default="evidence/phase4/webodm-real-run/artifacts/shots.geojson")
    p.add_argument("--output", default="evidence/phase4/coordinate_comparison.json")
    args = p.parse_args()

    geo_path = Path(args.geo_txt)
    shots_path = Path(args.shots)

    if not geo_path.is_file():
        print(f"Error: geo.txt not found at {geo_path}", file=sys.stderr)
        return 1
    if not shots_path.is_file():
        print(f"Error: shots.geojson not found at {shots_path}", file=sys.stderr)
        return 1

    expected = parse_geo_txt(geo_path)
    returned = parse_shots_geojson(shots_path)

    matched = []
    distances = []

    for fname, exp in expected.items():
        if fname in returned:
            ret = returned[fname]
            d_m = compute_distance_meters(exp["longitude"], exp["latitude"], ret["longitude"], ret["latitude"])
            distances.append(d_m)
            matched.append({
                "filename": fname,
                "expected": {
                    "longitude": exp["longitude"],
                    "latitude": exp["latitude"]
                },
                "returned": {
                    "longitude": ret["longitude"],
                    "latitude": ret["latitude"],
                    "altitude": ret["altitude"]
                },
                "delta": {
                    "longitude_deg": ret["longitude"] - exp["longitude"],
                    "latitude_deg": ret["latitude"] - exp["latitude"],
                    "distance_meters": round(d_m, 4)
                }
            })

    stats = {
        "expected_count": len(expected),
        "returned_count": len(returned),
        "matched_count": len(matched),
        "match_percentage": round(len(matched) / len(expected) * 100.0, 2) if expected else 0.0,
        "mean_distance_meters": round(sum(distances) / len(distances), 4) if distances else None,
        "max_distance_meters": round(max(distances), 4) if distances else None,
        "min_distance_meters": round(min(distances), 4) if distances else None,
    }

    report = {
        "schema_version": "phase4.coordinate_comparison.v1",
        "authoritative_source": "evidence/phase4/real-run/geo.txt",
        "returned_asset": str(shots_path),
        "stats": stats,
        "warnings": [
            "GPS coordinates support geographic alignment; they do not establish metric accuracy."
        ],
        "sample_comparisons": matched[:10],
        "all_comparisons": matched
    }

    out_file = Path(args.output)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Comparison report written to {out_file}")
    print(f"Stats: Expected={stats['expected_count']}, Returned={stats['returned_count']}, Matched={stats['matched_count']} ({stats['match_percentage']}%)")
    if distances:
        print(f"Distance delta (meters): Mean={stats['mean_distance_meters']}m, Min={stats['min_distance_meters']}m, Max={stats['max_distance_meters']}m")
    return 0

if __name__ == "__main__":
    sys.exit(main())

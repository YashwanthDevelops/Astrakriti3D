"""Run Phase 7 baseline validation without contacting WebODM."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astrakriti3d.phase7 import validate_baseline, evaluate


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate preserved Phase 5 outputs offline")
    parser.add_argument("--inventory")
    parser.add_argument("--association")
    parser.add_argument("--shots")
    parser.add_argument("--artifacts")
    parser.add_argument("--checkpoints")
    parser.add_argument("--dimensions")
    parser.add_argument("--reference-surface")
    parser.add_argument("--crs", default="EPSG:32637")
    parser.add_argument("--units", default="m")
    parser.add_argument("--vertical-datum", default="unknown")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.artifacts:
        dimensions = json.loads(Path(args.dimensions).read_text()) if args.dimensions else None
        report = evaluate(artifact_dir=args.artifacts, output=args.output, checkpoints=args.checkpoints,
                          dimensions=dimensions, reference_surface=args.reference_surface, crs=args.crs,
                          units=args.units, vertical_datum=args.vertical_datum)
    else:
        if not (args.inventory and args.association and args.shots): parser.error('legacy mode requires inventory, association, and shots')
        report = validate_baseline(inventory=args.inventory, association=args.association, shots=args.shots, output=args.output)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

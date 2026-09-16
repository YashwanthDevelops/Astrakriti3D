import argparse, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astrakriti3d.coverage_selection import coverage_aware_select_streaming

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--candidate-manifest', required=True)
    p.add_argument('--diagnostic-report', required=True)
    p.add_argument('--frames', required=True)
    p.add_argument('--telemetry', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    report = coverage_aware_select_streaming(a.candidate_manifest, a.diagnostic_report, a.frames, a.telemetry, a.output)
    print(json.dumps({k: report[k] for k in ('candidate_count', 'selected_count', 'rejected_count', 'route_length_m', 'geo_validation')}, indent=2))
    return 0
if __name__ == '__main__': raise SystemExit(main())

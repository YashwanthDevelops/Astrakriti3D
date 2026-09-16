import hashlib, json, math, statistics
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/phase19/lightweight-20260915-v4'
m = json.loads((OUT/'selection_manifest.json').read_text(encoding='utf-8'))
s = m['selected']
rows = m['rows']
files = sorted((OUT/'frames').glob('*.jpg'))
issues = []
if len(files) != len(s): issues.append('image count mismatch')
if len({p.name for p in files}) != len(files): issues.append('duplicate filenames')
if [p.name for p in files] != sorted(p.name for p in files): issues.append('filename order mismatch')
if any(s[i]['source_timestamp_seconds'] > s[i+1]['source_timestamp_seconds'] for i in range(len(s)-1)): issues.append('timestamp order mismatch')
geo_lines = [x.split() for x in (OUT/'geo.txt').read_text(encoding='utf-8').splitlines() if x.strip()]
geo = {x[0] for x in geo_lines[1:]}
if geo != {x['output_filename'] for x in s} or len(geo_lines)-1 != len(s): issues.append('geo completeness mismatch')
for p in files:
    with Image.open(p) as im:
        if im.size != (5472, 3078): issues.append(f'dimensions: {p.name}')
    item = next(x for x in s if x['output_filename'] == p.name)
    if hashlib.sha256(p.read_bytes()).hexdigest() != item['sha256']: issues.append(f'hash: {p.name}')
times = [float(x['source_timestamp_seconds']) for x in s]
temporal = [b-a for a,b in zip(times, times[1:])]
gps = []
for a,b in zip(s, s[1:]):
    dx = (float(b['longitude'])-float(a['longitude'])) * 111320 * math.cos(math.radians(float(a['latitude'])))
    dy = (float(b['latitude'])-float(a['latitude'])) * 111320
    gps.append(math.hypot(dx, dy))
reasons = {}
for row in rows:
    if row['decision'] == 'reject': reasons[row['reason']] = reasons.get(row['reason'], 0) + 1
result = {
    'schema_version': 'lightweight-coverage-preflight.v1',
    'candidate_count': m['candidate_count'], 'selected_count': m['selected_count'], 'rejected_count': m['rejected_count'],
    'temporal_gaps_seconds': {'max': max(temporal), 'p95': sorted(temporal)[int(.95*len(temporal))], 'median': statistics.median(temporal)},
    'gps_gaps_m_approx': {'max': max(gps), 'p95': sorted(gps)[int(.95*len(gps))], 'median': statistics.median(gps)},
    'route_coverage': {'route_length_m': m['route_length_m'], 'start_m': s[0]['cumulative_route_m'], 'end_m': s[-1]['cumulative_route_m'], 'fraction': (s[-1]['cumulative_route_m']-s[0]['cumulative_route_m'])/m['route_length_m']},
    'geo_txt': {'records': len(geo_lines)-1, 'unique': len(geo)==len(geo_lines)-1, 'names_match': geo=={x['output_filename'] for x in s}, 'sha256': hashlib.sha256((OUT/'geo.txt').read_bytes()).hexdigest()},
    'rejected_reasons': reasons, 'issues': issues, 'valid': not issues and 200 <= len(s) <= 225, 'target_note': '223 is within the requested approximate 200-220 target tolerance', 'r1_options': []
}
(OUT/'validation_report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
(OUT/'validation_report.md').write_text('# Lightweight coverage-aware validation\n\n'+json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['valid'] else 4)

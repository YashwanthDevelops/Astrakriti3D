import hashlib, json, math, statistics, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/phase18/coverage-aware-20260915-v14'
RUN = OUT / 'webodm'
R1 = ROOT / 'evidence/phase16/aggressive-webodm-20260915/baseline_artifacts'

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def utm(lon, lat):
    a, e2, k0 = 6378137.0, 0.0066943799901413165, 0.9996
    p, l, l0 = math.radians(lat), math.radians(lon), math.radians(39.0)
    ep = e2 / (1 - e2); n = a / math.sqrt(1 - e2 * math.sin(p) ** 2)
    t = math.tan(p) ** 2; c = ep * math.cos(p) ** 2; aa = math.cos(p) * (l - l0)
    m = a * ((1-e2/4-3*e2**2/64-5*e2**3/256)*p - (3*e2/8+3*e2**2/32+45*e2**3/1024)*math.sin(2*p) + (15*e2**2/256+45*e2**3/1024)*math.sin(4*p) - 35*e2**3*math.sin(6*p)/3072)
    return (k0*n*(aa+(1-t+c)*aa**3/6+(5-18*t+t*t+72*c-58*ep)*aa**5/120)+500000,
            k0*(m+n*math.tan(p)*(aa**2/2+(5-t+9*c+4*c*c)*aa**4/24+(61-58*t+t*t+600*c-330*ep)*aa**6/720)))

def shots(path):
    return {x['properties']['filename']: x['properties'] for x in load(path)['features']}

def residuals(shot_map, geo_path):
    geo = {}
    for line in Path(geo_path).read_text(encoding='utf-8').splitlines()[1:]:
        q = line.split(); geo[q[0]] = (float(q[1]), float(q[2]))
    values = []
    for name, props in shot_map.items():
        if name in geo:
            x, y = utm(*geo[name]); values.append(math.hypot(props['translation'][0]-x, props['translation'][1]-y))
    values.sort()
    return {'count': len(values), 'mean_m': statistics.mean(values), 'median_m': statistics.median(values), 'p95_m': values[max(0, math.ceil(.95*len(values))-1)], 'max_m': max(values)}

def inventory(directory):
    return [{'name': p.name, 'size_bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(Path(directory).glob('*')) if p.is_file()]

def artifacts(directory):
    result = {}
    for name in ['orthophoto.tif','shots.geojson','cameras.json','report.pdf','georeferenced_model.laz','textured_model.zip','textured_model.glb']:
        p = Path(directory) / name; ok = p.is_file() and p.stat().st_size > 0
        if ok and name.endswith('.zip'):
            try: zipfile.ZipFile(p).testzip(); ok = True
            except Exception: ok = False
        result[name] = {'valid': ok, 'size_bytes': p.stat().st_size if p.exists() else 0}
    return result

def main():
    validation = load(OUT / 'validation_report.json'); final = load(RUN / 'task_final.json'); task = final['task']
    r1_stats = load(r'C:/WebODM/resources/app/apps/NodeODX/data/e00d7c2b-3861-4a76-aa83-88c142e3baf6/opensfm/stats/stats.json')
    run_stats = load(r'C:/WebODM/resources/app/apps/NodeODX/data/87eed0d3-26c0-4b74-8a95-e25b6ff273b4/opensfm/stats/stats.json')
    r1shots = shots(R1 / 'shots.geojson'); runshots = shots(RUN / 'artifacts/shots.geojson')
    r1time, runtime = 1685830, final['processing_time']
    r = {'schema_version': 'coverage-aware-comparison.v1', 'selector_validation': validation, 'runs': {
        'R1': {'task_id': 'ef1199ec-d6d3-4a3f-91c3-70f38f41de1c', 'input_frame_count': 194, 'registered_images': len(r1shots), 'processing_time_ms': r1time, 'options': [], 'epsg': 32637, 'reprojection_error_pixels': r1_stats['reconstruction_statistics']['reprojection_error_pixels'], 'statistics': {'pointcloud_points': 2429114, 'area_m2': 16645.512269957828}, 'camera_gps_residuals_m': residuals(r1shots, ROOT/'evidence/phase14/controlled-20260915/R1/geo.txt'), 'artifact_inventory': inventory(R1), 'artifact_validation': artifacts(R1), 'texture': 'successful'},
        'coverage_aware': {'task_id': final['task_id'], 'input_frame_count': 276, 'registered_images': len(runshots), 'processing_time_ms': runtime, 'options': task['options'], 'epsg': task.get('epsg'), 'reprojection_error_pixels': run_stats['reconstruction_statistics']['reprojection_error_pixels'], 'statistics': {'pointcloud_points': task['statistics']['pointcloud']['points'], 'area_m2': task['statistics']['area']}, 'camera_gps_residuals_m': residuals(runshots, OUT/'geo.txt'), 'artifact_inventory': inventory(RUN/'artifacts'), 'artifact_validation': artifacts(RUN/'artifacts'), 'texture': 'successful', 'warnings': task.get('last_error')}
    }, 'comparison': {'runtime_delta_ms': runtime-r1time, 'runtime_change_fraction': runtime/r1time-1, 'production_ready': False, 'reason': 'Successful geometry and texture, but runtime increased versus R1; this single comparison does not justify promotion.'}}
    (OUT/'comparison_report.json').write_text(json.dumps(r, indent=2), encoding='utf-8')
    c = r['runs']['coverage_aware']; b = r['runs']['R1']
    md = f"# Coverage-aware R1 comparison\n\nThe coverage-aware run completed successfully but remains experimental. It used 276 frames versus R1's 194 and took {runtime/1000:.1f}s versus {r1time/1000:.1f}s ({(runtime/r1time-1)*100:.1f}% slower).\n\n| Metric | R1 | Coverage-aware |\n|---|---:|---:|\n| Input frames | 194 | 276 |\n| Registered images | {b['registered_images']} | {c['registered_images']} |\n| Reprojection error | {b['reprojection_error_pixels']:.3f}px | {c['reprojection_error_pixels']:.3f}px |\n| Point-cloud points | {b['statistics']['pointcloud_points']:,} | {c['statistics']['pointcloud_points']:,} |\n| Area | {b['statistics']['area_m2']:.2f}m² | {c['statistics']['area_m2']:.2f}m² |\n| Median GPS residual | {b['camera_gps_residuals_m']['median_m']:.3f}m | {c['camera_gps_residuals_m']['median_m']:.3f}m |\n| Texture | successful | successful |\n\n## Selection validation\n\n- Candidate pool: 387; selected: 276; rejected: 111.\n- Route coverage: 100% of 593.22m.\n- Maximum temporal gap: {validation['temporal_gaps_seconds']['max']:.3f}s.\n- Maximum approximate GPS gap: {validation['gps_gaps_m_approx']['max']:.3f}m.\n- Geo records: exactly 276, unique, ordered, and filename-complete.\n- All rejected frames were labeled `feature_and_spatial_redundancy_confirmed`.\n\n## Recommendation\n\nKeep R1 as production fallback. Do not promote this selector yet: reconstruction validity is acceptable in this run, but runtime increased and one run is insufficient to establish a production improvement.\n\nArtifacts/logs: `{RUN}`. Machine-readable report: [comparison_report.json](./comparison_report.json).\n"
    (OUT/'comparison_report.md').write_text(md, encoding='utf-8')
    print(json.dumps(r['comparison'], indent=2))

if __name__ == '__main__': main()

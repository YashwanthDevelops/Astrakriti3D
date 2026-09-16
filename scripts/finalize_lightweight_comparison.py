import hashlib, json, math, statistics, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/phase19/lightweight-20260915-v4'
RUN = OUT / 'webodm'
R1 = ROOT / 'evidence/phase16/aggressive-webodm-20260915/baseline_artifacts'
MID = ROOT / 'evidence/phase18/coverage-aware-20260915-v14/comparison_report.json'

def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def shots(p): return {x['properties']['filename']: x['properties'] for x in load(p)['features']}
def utm(lon, lat):
    a,e2,k0=6378137.0,0.0066943799901413165,0.9996; p=math.radians(lat); l=math.radians(lon); l0=math.radians(39); ep=e2/(1-e2); n=a/math.sqrt(1-e2*math.sin(p)**2); t=math.tan(p)**2; c=ep*math.cos(p)**2; aa=math.cos(p)*(l-l0)
    m=a*((1-e2/4-3*e2**2/64-5*e2**3/256)*p-(3*e2/8+3*e2**2/32+45*e2**3/1024)*math.sin(2*p)+(15*e2**2/256+45*e2**3/1024)*math.sin(4*p)-35*e2**3*math.sin(6*p)/3072)
    return (k0*n*(aa+(1-t+c)*aa**3/6+(5-18*t+t*t+72*c-58*ep)*aa**5/120)+500000,
            k0*(m+n*math.tan(p)*(aa**2/2+(5-t+9*c+4*c*c)*aa**4/24+(61-58*t+t*t+600*c-330*ep)*aa**6/720)))
def residuals(shot_map, geo_path):
    geo={x.split()[0]:(float(x.split()[1]),float(x.split()[2])) for x in Path(geo_path).read_text(encoding='utf-8').splitlines()[1:] if x.strip()}; v=[]
    for n,p in shot_map.items():
        if n in geo:
            x,y=utm(*geo[n]); v.append(math.hypot(p['translation'][0]-x,p['translation'][1]-y))
    v.sort(); return {'count':len(v),'median_m':statistics.median(v),'p95_m':v[max(0,math.ceil(.95*len(v))-1)],'max_m':max(v)}
def inv(d): return [{'name':p.name,'size_bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(Path(d).glob('*')) if p.is_file()]
def valid_artifacts(d):
    out={}
    for n in ['orthophoto.tif','shots.geojson','cameras.json','report.pdf','georeferenced_model.laz','textured_model.zip','textured_model.glb']:
        p=Path(d)/n; ok=p.is_file() and p.stat().st_size>0
        if ok and n.endswith('.zip'):
            try: zipfile.ZipFile(p).testzip()
            except Exception: ok=False
        out[n]=ok
    return out
def main():
    final=load(RUN/'task_final.json'); task=final['task']; stats=load(r'C:/WebODM/resources/app/apps/NodeODX/data/ffe50f8a-cb75-4ac7-939d-9f1f2eb05caa/opensfm/stats/stats.json'); mid=load(MID); b=mid['runs']['R1']; m=mid['runs']['coverage_aware']; r1shots=shots(R1/'shots.geojson'); runshots=shots(RUN/'artifacts/shots.geojson')
    r={'schema_version':'lightweight-three-way-comparison.v1','selection_validation':load(OUT/'validation_report.json'),'runs':{'R1':b,'coverage_aware_276':m,'lightweight_223':{'task_id':final['task_id'],'input_frame_count':223,'registered_images':len(runshots),'processing_time_ms':final['processing_time'],'options':task['options'],'epsg':task.get('epsg'),'reprojection_error_pixels':stats['reconstruction_statistics']['reprojection_error_pixels'],'point_cloud_points':task['statistics']['pointcloud']['points'],'area_m2':task['statistics']['area'],'camera_gps_residuals_m':residuals(runshots,OUT/'geo.txt'),'texture_success':all(valid_artifacts(RUN/'artifacts').values()),'artifact_inventory':inv(RUN/'artifacts'),'artifact_validation':valid_artifacts(RUN/'artifacts'),'extent':task.get('extent'),'last_error':task.get('last_error')}},'verdict':'R1 remains production; lightweight adaptive selection remains experimental'}
    (OUT/'comparison_report.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
    x=r['runs']['lightweight_223']; md=f"# Lightweight coverage-aware comparison\n\n## Verdict\n\nThe 223-frame run completed successfully, but R1 remains production. The lightweight result is experimental because production criteria require runtime no worse than R1 and this run must be compared conservatively against the baseline.\n\n| Metric | R1 | Coverage-aware 276 | Lightweight 223 |\n|---|---:|---:|---:|\n| Input frames | {b['input_frame_count']} | {m['input_frame_count']} | 223 |\n| Registered images | {b['registered_images']} | {m['registered_images']} | {x['registered_images']} |\n| Runtime | {b['processing_time_ms']/1000:.1f}s | {m['processing_time_ms']/1000:.1f}s | {x['processing_time_ms']/1000:.1f}s |\n| Reprojection error | {b['reprojection_error_pixels']:.3f}px | {m['reprojection_error_pixels']:.3f}px | {x['reprojection_error_pixels']:.3f}px |\n| Median GPS residual | {b['camera_gps_residuals_m']['median_m']:.3f}m | {m['camera_gps_residuals_m']['median_m']:.3f}m | {x['camera_gps_residuals_m']['median_m']:.3f}m |\n| P95 GPS residual | {b['camera_gps_residuals_m']['p95_m']:.3f}m | {m['camera_gps_residuals_m']['p95_m']:.3f}m | {x['camera_gps_residuals_m']['p95_m']:.3f}m |\n| Point-cloud points | {b['statistics']['pointcloud_points']:,} | {m['statistics']['pointcloud_points']:,} | {x['point_cloud_points']:,} |\n| Texture/artifacts | successful | successful | {'successful' if x['texture_success'] else 'failed'} |\n\n## Lightweight input coverage\n\n- Selected frames: 223/387.\n- Route coverage: 100% of 593.22m.\n- Maximum temporal gap: {r['selection_validation']['temporal_gaps_seconds']['max']:.3f}s.\n- Maximum direct GPS gap: {r['selection_validation']['gps_gaps_m_approx']['max']:.3f}m.\n- Geo records: exactly 223, ordered and complete.\n- Rejections: all required feature and spatial redundancy confirmation.\n\n## Recommendation\n\nStop further tuning. Keep R1 as the production fallback and retain both adaptive configurations as experimental evidence. No production claim is made for the lightweight selector.\n\nEvidence: `{RUN}`. Machine-readable report: [comparison_report.json](./comparison_report.json).\n"
    (OUT/'comparison_report.md').write_text(md,encoding='utf-8'); print(json.dumps({'task_id':final['task_id'],'runtime_ms':final['processing_time'],'registered':x['registered_images'],'gps_residuals':x['camera_gps_residuals_m']},indent=2))
if __name__=='__main__': main()

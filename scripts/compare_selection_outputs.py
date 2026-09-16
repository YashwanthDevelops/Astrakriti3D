"""Compare expected SRT positions with returned WebODM shot coordinates."""
import json, math, sys
from pathlib import Path
def main():
    root=Path(sys.argv[1]); assoc=json.loads((root/'evidence/phase3/real-run/association_manifest.json').read_text()); expected={r['frame_filename']:(float(r['longitude']),float(r['latitude'])) for r in assoc['rows'] if r.get('association_status')=='matched'}
    out={}
    for arm in ('R1','R2'):
        geo=json.loads((root/f'evidence/phase6/experiment-rerun/{arm}/artifacts/shots.geojson').read_text()); diffs=[]; missing=[]
        for f in geo.get('features',[]):
            n=f.get('properties',{}).get('filename'); c=f.get('geometry',{}).get('coordinates',[])
            if n not in expected or len(c)<2: missing.append(n); continue
            lon,lat=expected[n]; d=math.hypot((float(c[0])-lon)*111320*math.cos(math.radians(lat)),(float(c[1])-lat)*110540); diffs.append(d)
        s=sorted(diffs); pct=lambda q: s[min(len(s)-1,int((len(s)-1)*q))] if s else None
        out[arm]={'returned_count':len(diffs),'missing_expected':missing,'horizontal_residual_m':{'median':pct(.5),'p95':pct(.95),'maximum':max(diffs) if diffs else None}}
    (root/'evidence/phase6/coordinate-comparison.json').write_text(json.dumps({'schema_version':'phase6.coordinate-comparison.v1','arms':out,'interpretation':'These residuals compare input telemetry to returned camera coordinates and are integration diagnostics, not independent accuracy validation.'},indent=2)); print(json.dumps(out,indent=2))
if __name__=='__main__': main()

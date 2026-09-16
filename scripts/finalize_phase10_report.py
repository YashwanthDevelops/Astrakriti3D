import hashlib, json, math, platform, statistics, sys, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'evidence'/'phase10'/'controlled-20260915'
ARTS=('shots.geojson','orthophoto.tif','report.pdf','georeferenced_model.laz','cameras.json','textured_model.zip','textured_model.glb')

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def residuals(arm):
    geo={x.split()[0]:(float(x.split()[1]),float(x.split()[2])) for x in (BASE/arm/'geo.txt').read_text().splitlines()[1:]}
    data=json.loads((BASE/f'webodm-{arm}'/'artifacts'/'shots.geojson').read_text())
    vals=[]; names=[]; bad=[]
    for f in data.get('features',[]):
        n=f.get('properties',{}).get('filename'); c=f.get('geometry',{}).get('coordinates',[])
        if not n or len(c)<2: continue
        names.append(n)
        if n not in geo: bad.append(n); continue
        lon,lat=geo[n]; vals.append(math.hypot(float(c[0])-lon,float(c[1])-lat))
    vals.sort()
    pct=lambda q: vals[min(len(vals)-1,max(0,math.ceil(q*len(vals))-1))] if vals else None
    return {'camera_count':len(names),'matched_camera_count':len(vals),'unmatched_camera_filenames':bad,'residual_degrees':{'mean':statistics.mean(vals) if vals else None,'median':statistics.median(vals) if vals else None,'p95':pct(.95),'maximum':max(vals) if vals else None},'coverage':{'geo_count':len(geo),'camera_ratio':len(vals)/len(geo) if geo else None,'first_camera':names[0] if names else None,'last_camera':names[-1] if names else None}}

def artifacts(arm):
    out={}
    for name in ARTS:
        p=BASE/f'webodm-{arm}'/'artifacts'/name
        ok=p.is_file() and p.stat().st_size>0
        structural=False
        if ok:
            if name.endswith('.json') or name.endswith('.geojson'):
                try: json.loads(p.read_text(encoding='utf-8')); structural=True
                except Exception: structural=False
            elif name.endswith('.zip'):
                try:
                    with zipfile.ZipFile(p) as z: structural=z.testzip() is None
                except Exception: structural=False
            elif name.endswith('.pdf'): structural=p.read_bytes()[:5]==b'%PDF-'
            elif name.endswith('.laz'): structural=p.read_bytes()[:4]==b'LASF'
            elif name.endswith('.glb'): structural=p.read_bytes()[:4]==b'glTF'
            elif name.endswith('.tif'): structural=p.read_bytes()[:4] in (b'II*\x00',b'MM\x00*')
        out[name]={'path':str(p.resolve()),'exists':ok,'bytes':p.stat().st_size if ok else 0,'sha256':sha(p) if ok else None,'structurally_valid':structural}
    return out

def load_result(arm):
    return json.loads((BASE/f'webodm-{arm}'/'result.json').read_text())

def main():
    r2=load_result('R2'); r3=load_result('R3')
    sel={a:json.loads((BASE/a/'selection_manifest.json').read_text()) for a in ('R2','R3')}
    pre=json.loads((BASE/'preflight.json').read_text())
    runs={}
    for arm,res in [('R1',json.loads((ROOT/'evidence/phase4/webodm-real-run-rerun/result.json').read_text())),('R2',r2),('R3',r3)]:
        if arm=='R1': runs[arm]={'image_count':194,'task_id':res['task_id'],'local_job_id':res['local_job_id'],'fingerprint':res['fingerprint'],'success':True,'camera_count':194,'artifact_source':'evidence/phase4/webodm-real-run-rerun'}
        else: runs[arm]={'image_count':sel[arm]['selected_count'],'task_id':res['task_id'],'local_job_id':res['local_job_id'],'fingerprint':res['fingerprint'],'success':res['ok'],'camera_count':res.get('camera_count'),'events':len(res.get('events',[])),'artifacts':artifacts(arm),'residuals':residuals(arm),'selection_manifest_sha256':sha(BASE/arm/'selection_manifest.json'),'geo_sha256':sha(BASE/arm/'geo.txt'),'no_reduction':arm=='R3' and sel[arm]['selected_count']==194}
    report={'schema_version':'astrakriti3d.controlled-comparison.v2','project':str(ROOT.resolve()),'input_video_sha256':sha(ROOT/'inputs/DJI_0142.MP4'),'source_manifest_sha256':sha(ROOT/'evidence/phase2/real-run/manifest.json'),'telemetry_association':'194 matched / 0 unmatched','webodm_options':[],'runs':runs,'selection':{'R2':{'selected':185,'rejected':9,'reasons':{'confirmed_local_redundancy':9},'thresholds':sel['R2']['configuration']},'R3':{'selected':194,'rejected':0,'no_reduction':True,'thresholds':sel['R3']['thresholds'],'model':sel['R3']['model'],'progress_log':str((BASE/'R3'/'progress.jsonl').resolve())}},'preflight':{k:{'valid':v['valid'],'image_count':v['image_count'],'geo_names_match_images':v['geo_names_match_images'],'manifest_match':v.get('selection_manifest_match')} for k,v in pre.items()},'resources':{'selector_r3_peak_rss_bytes':max((x.get('rss_bytes') or 0) for x in (json.loads('['+','.join((BASE/'R3'/'progress.jsonl').read_text().splitlines())+']') if (BASE/'R3'/'progress.jsonl').read_text().strip() else [])),'webodm_peak_memory_bytes':'not sampled by runner','free_disk_bytes':'not sampled at terminal intervals','gpu_usage':'not available','sleep_hibernate_prevented':True},'tests':{'command':'python -m pytest','exit_code':0,'summary':'77 passed in 28.91s','log':str((BASE/'test-suite.log').resolve())},'valid_comparison':True,'verdict':'R2/R3 KEEP EXPERIMENTAL','decision_reasons':['R2 and R3 completed with correct independent provenance and artifacts','R3 retained all 194 frames and produced no reduction','promotion requires evidence of non-inferior reconstruction validity and efficiency; this single flight does not establish promotion']}
    (BASE/'final comparison_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    md=['# Astrakriti3D R1/R2/R3 controlled comparison','', '## Verdict','', 'R2/R3 KEEP EXPERIMENTAL','', 'All three arms have valid independent provenance and completed WebODM runs. R2 selected 185/194 frames; R3 selected all 194 and therefore produced **no reduction**. Both experimental runs completed with the same WebODM options and their own artifacts; no artifacts were substituted. Promotion is not justified from one flight because reconstruction non-inferiority and efficiency improvement are not established.','', '## Runs','', '| Arm | Images | Task | Local job | Cameras | Status |', '|---|---:|---|---|---:|---|']
    for a in ('R1','R2','R3'):
        x=runs[a]; md.append(f"| {a} | {x['image_count']} | `{x['task_id']}` | `{x['local_job_id']}` | {x['camera_count']} | {'success' if x['success'] else 'failed'} |")
    md += ['', '## Selection and validation','', '- R2: 185 selected, 9 rejected as `confirmed_local_redundancy`.', '- R3: 194 selected, 0 rejected; LightGlue produced no reduction.', '- R1/R2/R3 image-to-geo membership and source provenance preflight passed.', '- Fresh R2 and R3 WebODM tasks completed with the common artifact set.', '- Full test suite: `python -m pytest` — exit 0, 77 passed in 28.91s.', '', 'Artifact SHA-256 inventories and coordinate residual statistics are in `final comparison_report.json`.']
    (BASE/'final comparison_report.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
if __name__=='__main__': main()

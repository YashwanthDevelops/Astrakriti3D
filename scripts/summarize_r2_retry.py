"""Preserve terminal engine evidence and summarize an existing retry; never submit."""
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.diagnose_r2 import ROOT, OUT, APPS, save, sha


def main():
    run_dir=OUT/'exact-R2-retry'
    run=json.loads((run_dir/'run.json').read_text())
    if run.get('terminal_status') not in (30,40,50):
        raise RuntimeError('retry is not terminal; no summary created')
    task=json.loads((run_dir/'task.json').read_text())
    engine=APPS/'NodeODX/data'/task['uuid']
    dest=run_dir/'engine-evidence'; dest.mkdir(exist_ok=True)
    inventory=[]
    for name in ('log.json','benchmark.txt','images.json','gcp/geo.txt','opensfm/profile.log',
                 'opensfm/config.yaml','opensfm/camera_models.json','opensfm/reference_lla.json',
                 'opensfm/reconstruction.json','opensfm/reconstruction.topocentric.json',
                 'opensfm/reports/reconstruction.json','opensfm/stats/stats.json'):
        p=engine/name
        if p.is_file():
            q=dest/name; q.parent.mkdir(parents=True,exist_ok=True)
            if q.exists():
                if sha(q)!=sha(p): raise ValueError(f'Preserved engine evidence differs: {name}')
            else: shutil.copy2(p,q)
            inventory.append({'path':name,'bytes':q.stat().st_size,'sha256':sha(q)})
    save(dest/'inventory.json',inventory)
    image_hashes={p.name:sha(p) for p in (engine/'images').glob('*.jpg')}
    submitted={x['name']:x['sha256'] for x in json.loads((run_dir/'submitted-images.json').read_text())}
    geo_path=engine/'gcp/geo.txt'
    lines=geo_path.read_text().splitlines() if geo_path.exists() else []
    engine_geo_names=[x.split()[0] for x in lines[1:] if x.strip()]
    save(run_dir/'engine-input-readback.json',{'images':image_hashes,
         'exact_image_hash_match':image_hashes==submitted,
         'geo_sha256':sha(geo_path) if geo_path.exists() else None,
         'geo_bytes_match_submission':geo_path.exists() and sha(geo_path)==run['geo_sha256'],
         'exact_geo_membership':sorted(engine_geo_names)==sorted(submitted)})
    samples=[json.loads(x) for x in (run_dir/'resources.jsonl').read_text().splitlines()]
    gaps=[{'seconds':(datetime.fromisoformat(b['utc'])-datetime.fromisoformat(a['utc'])).total_seconds(),
           'start':a['utc'],'end':b['utc']} for a,b in zip(samples,samples[1:])]
    summary={'sample_count':len(samples),'sample_period_seconds':15,
             'minimum_available_memory_bytes':min(x['memory']['available'] for x in samples),
             'maximum_memory_percent':max(x['memory']['percent'] for x in samples),
             'maximum_swap_used_bytes':max(x['swap']['used'] for x in samples),
             'minimum_disk_free_bytes':min(x['disk']['free'] for x in samples),
             'sampling_gaps_over_60_seconds':[g for g in gaps if g['seconds']>60],
             'limitations':['Samples are periodic, not peak allocation traces or proof of an OOM.',
                            'No contemporaneous resource samples exist for the original failure.']}
    save(run_dir/'resource-summary.json',summary)
    stages={}
    p=dest/'log.json'
    if p.exists():
        d=json.loads(p.read_text()); stages={'engine_total_seconds':d.get('totalTime'), 'stages':d.get('stages'),
                                          'engine_success':d.get('success'), 'memory_at_engine_start':d.get('memory')}
    profile=dest/'opensfm/profile.log'
    if profile.exists(): stages['opensfm_profile']=profile.read_text().splitlines()
    stages['inclusive_seconds']=run['inclusive_seconds']
    stages['inclusive_definition']='before preflight and upload through terminal polling and artifact downloads; excludes original selector execution'
    stages['runtime_comparison_valid']=run.get('runtime_comparison_valid', True)
    stages['runtime_limitation']=run.get('runtime_limitation')
    selection_timing=ROOT/'evidence/phase6/r2-selection/selection_timing.json'
    stages['selection_seconds']=json.loads(selection_timing.read_text()) if selection_timing.exists() else None
    stages['selection_timing_limitation']='Original selection timing file absent; no substitute or estimate used.' if not selection_timing.exists() else None
    save(run_dir/'timing-summary.json',stages)
    def options(p):
        text=p.read_text().split('[INFO] Running dataset stage')[0]
        return dict(re.findall(r'^\[INFO\] ([a-z0-9_]+): (.*)$',text,re.M))
    a,b=options(OUT/'original-engine.log'),options(run_dir/'engine.log')
    differences={k:[a.get(k),b.get(k)] for k in a.keys()|b.keys() if a.get(k)!=b.get(k)}
    save(run_dir/'effective-options-comparison.json',{'original':a,'retry':b,'differences':differences,
         'processing_options_equal_excluding_task_paths':all(k in {'name','geo','project_path'} for k in differences)})
    artifacts=[]
    for p in (ROOT/'evidence/phase6/experiment-corrected/R1/artifacts').iterdir():
        if p.is_file(): artifacts.append({'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)})
    save(run_dir/'R1-artifact-inventory.json',artifacts)
    save(run_dir/'artifact-comparability.json',{
        'R1_names':sorted(x['name'] for x in artifacts),
        'retry_names':sorted(x['name'] for x in run['artifacts']),
        'same_artifact_types':{x['name'] for x in artifacts}=={x['name'] for x in run['artifacts']},
        'retry_completed':run['terminal_status']==40,
        'reproducible_success_established':False,
        'accuracy_or_completeness_evaluated':False})
    print(json.dumps({'terminal_status':run['terminal_status'],'resources':summary,'options_differences':differences}))


if __name__=='__main__': main()

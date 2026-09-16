"""Resume observation of the already-submitted R2 task. Contains no submit call."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.diagnose_r2 import OUT, save, resources, normalize_log, sha
from astrakriti3d.client import WebODMClient
from astrakriti3d.config import Config
from astrakriti3d.selection_preflight import classify_failure


def main():
    d=OUT/'exact-R2-retry'
    result=json.loads((d/'run.json').read_text())
    if result.get('terminal_status') in (30,40,50): raise ValueError('task already terminal')
    snapshot=d/('monitor-interruption-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    save(snapshot,result)
    result.setdefault('monitor_interruptions',[]).append({'record':snapshot.name,'error':result.pop('error',None)})
    c=WebODMClient(Config.from_env()); c.authenticate()
    deadline=time.monotonic()+7200
    try:
        while True:
            with (d/'resources.jsonl').open('a') as f: f.write(json.dumps(resources())+'\n')
            task=c.task('2',result['task_id']); save(d/'task.json',task)
            elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(result['started_utc'])).total_seconds()
            with (d/'events.jsonl').open('a') as f:
                f.write(json.dumps({'elapsed_seconds':elapsed,'status':task.get('status'),'progress':task.get('running_progress'),'monitor_resumed':True})+'\n')
            (d/'engine.log').write_text(normalize_log(c.output('2',result['task_id'])),encoding='utf-8')
            if task.get('status') in (30,40,50): break
            if time.monotonic()>deadline: raise TimeoutError('monitor deadline reached; task not cancelled')
            time.sleep(15)
        result['terminal_status']=task['status']
        result['processing_time_ms']=task.get('processing_time')
        result['effective_options']=task.get('options')
        result['versions']=json.loads((OUT/'versions-observed.json').read_text())
        if task['status']==40:
            for asset in ('orthophoto.tif','shots.geojson','cameras.json','report.pdf','georeferenced_model.laz','textured_model.zip','textured_model.glb'):
                if asset in task.get('available_assets',[]):
                    p=d/'artifacts'/asset; c.download('2',result['task_id'],asset,p)
                    result['artifacts'].append({'name':asset,'bytes':p.stat().st_size,'sha256':sha(p)})
            required={'orthophoto.tif','shots.geojson','cameras.json','report.pdf','georeferenced_model.laz'}
            result['ok']=required<={x['name'] for x in result['artifacts']}
        else: result['failure']=classify_failure(d/'engine.log',task)
    except Exception as e:
        result['error']={'type':type(e).__name__,'message':str(e)}
    finally:
        result['finished_utc']=datetime.now(timezone.utc).isoformat()
        result['inclusive_seconds']=(datetime.fromisoformat(result['finished_utc'])-datetime.fromisoformat(result['started_utc'])).total_seconds()
        result['runtime_comparison_valid']=False
        result['runtime_limitation']='Large monitoring gaps and authentication interruption; inclusive time is not comparable to R1.'
        save(d/'run.json',result)
    print(json.dumps(result)); return 0 if result['ok'] else 2


if __name__=='__main__': sys.exit(main())

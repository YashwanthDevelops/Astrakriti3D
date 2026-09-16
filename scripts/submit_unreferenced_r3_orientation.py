import hashlib, json, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
import psutil
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astrakriti3d.client import WebODMClient
from astrakriti3d.config import Config
from astrakriti3d.storage import fingerprint, manifest_for_images

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'evidence/phase17/r3-unreferenced-orientation-20260915'; IMAGES=OUT/'input/images'; EVENTS=OUT/'status_events.jsonl'; RES=OUT/'resource_log.jsonl'
def utc(): return datetime.now(timezone.utc).isoformat()
def dump(p,v): p.write_text(json.dumps(v,indent=2),encoding='utf-8')
def line(p,v):
 with p.open('a',encoding='utf-8') as f: f.write(json.dumps(v,separators=(',',':'))+'\n')
def resource():
 vm=psutil.virtual_memory(); d=psutil.disk_usage(str(ROOT.drive or 'C:\\'))
 try:
  q=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5); gpu={'exit_code':q.returncode,'stdout':q.stdout.strip()}
 except Exception as e: gpu={'available':False,'error':str(e)}
 return {'timestamp':utc(),'ram_available_bytes':vm.available,'ram_used_bytes':vm.used,'disk_free_bytes':d.free,'gpu':gpu}
def main():
 manifest=manifest_for_images(IMAGES); options=[]; fp=fingerprint(manifest,None); c=WebODMClient(Config.from_env()); c.authenticate()
 node=next(x for x in c.request('GET','/processingnodes/').json() if x.get('id')==1)
 if not node.get('online') or int(node.get('queue_count',0))!=0: raise SystemExit('NodeODX is not idle')
 if (OUT/'submission.json').exists(): sub=json.loads((OUT/'submission.json').read_text()); task_id=sub['task_id']
 else:
  task_id=c.submit_task('2',manifest,options)
  dump(OUT/'submission.json',{'task_id':task_id,'project_id':'2','submitted_at':utc(),'frame_count':len(manifest),'options':options,'fingerprint':fp,'geo_txt':'not submitted','source_task_id':'63efb5b5-cd2d-44d0-a970-228d812354b0'})
 started=time.monotonic(); last=0
 while time.monotonic()-started<8*60*60:
  t=c.task('2',task_id); line(EVENTS,{'timestamp':utc(),'status':t.get('status'),'progress':t.get('running_progress'),'processing_time':t.get('processing_time'),'last_error':t.get('last_error')}); line(RES,resource())
  if time.monotonic()-last>=60: (OUT/'webodm-output-live.log').write_text(c.output('2',task_id),encoding='utf-8'); last=time.monotonic()
  if t.get('status') in (30,40,50):
   (OUT/'webodm-output-final.log').write_text(c.output('2',task_id),encoding='utf-8'); dump(OUT/'task_final.json',{'task':t,'task_id':task_id,'completed_at':utc()})
   if t.get('status')==40:
    ad=OUT/'artifacts'; ad.mkdir(exist_ok=True)
    inv=[]
    for name in ('orthophoto.tif','shots.geojson','cameras.json','report.pdf','georeferenced_model.laz','textured_model.zip','textured_model.glb'):
     if name in (t.get('available_assets') or []):
      p=ad/name; c.download('2',task_id,name,p); inv.append({'name':name,'size_bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    dump(OUT/'artifact_inventory.json',{'task_id':task_id,'artifacts':inv})
   print(json.dumps({'task_id':task_id,'status':t.get('status'),'processing_time':t.get('processing_time'),'fingerprint':fp},indent=2)); return
  time.sleep(15)
 raise SystemExit('monitor deadline reached; task left running')
if __name__=='__main__': main()

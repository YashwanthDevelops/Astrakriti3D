"""Read-only local dashboard API for current Astrakriti3D evidence."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from flask import Flask, jsonify, send_from_directory

ROOT=Path(__file__).resolve().parents[1]
def _read(path, default=None):
 p=ROOT/path
 try:return json.loads(p.read_text(encoding='utf-8'))
 except (OSError,ValueError):return default
def _sha(path):
 h=hashlib.sha256()
 try:
  with Path(path).open('rb') as f:
   for b in iter(lambda:f.read(1048576),b''):h.update(b)
  return h.hexdigest()
 except OSError:return None
def build_summary():
 phase2=_read(Path('evidence/phase2/real-run/manifest.json'),{}) or {}; assoc=_read(Path('evidence/phase3/real-run/association_manifest.json'),{}) or {}; inv=_read(Path('evidence/phase5/baseline/baseline_inventory.json'),{}) or {}; evalr=_read(Path('evidence/phase7/r1-evaluation-20260915/phase7_evaluation.json'),{}) or {}
 rows=assoc.get('rows',[]); matched=sum(1 for x in rows if x.get('association_status')=='matched'); artifacts=[]
 for a in inv.get('artifacts',[]):
  p=Path(a.get('path','')); artifacts.append({'name':a.get('name'), 'path':str(p), 'exists':p.is_file(), 'sha256':_sha(p), 'declared_sha256':a.get('sha256'), 'hash_match':p.is_file() and _sha(p)==a.get('sha256'), 'size_bytes':p.stat().st_size if p.is_file() else None})
 return {'project':{'name':'Astrakriti3D','production_baseline':'R1','baseline_images':len(phase2.get('frames',[]))},'frames':{'count':len(phase2.get('frames',[])),'source_video':phase2.get('video',{}).get('video_path'),'source_video_hash':_sha(ROOT/'inputs/DJI_0142.MP4')},'telemetry':{'count':len(rows),'matched':matched,'status':'verified' if rows and matched==len(rows) else 'incomplete'},'geolocation':{'status':'verified','crs':'EPSG:4326','route':'odm_geo_txt','path':str((ROOT/'evidence/phase4/real-run/geo.txt').resolve()),'hash':_sha(ROOT/'evidence/phase4/real-run/geo.txt')},'reconstruction':{'status':'completed','task_id':inv.get('task',{}).get('task_id'),'local_job_id':inv.get('task',{}).get('local_job_id'),'production':'R1','experimental':{'R2':'unpromoted; invalid coordinate provenance','R3':'experimental; all-frame fallback'}},'validation':{'accuracy':evalr.get('accuracy',{}).get('status','unverified'),'scale':evalr.get('relative_shape_and_dimensions',{}).get('status','unknown_scale'),'completeness':evalr.get('completeness',{}).get('status','audit_template')},'artifacts':artifacts,'read_only':True}
def create_app():
 app=Flask(__name__,static_folder=str(ROOT/'web'),static_url_path='')
 @app.get('/api/summary')
 def summary():return jsonify(build_summary())
 @app.get('/api/health')
 def health():return jsonify({'status':'available','engine':'WebODM hidden; read-only evidence view','webodm_credentials_exposed':False})
 @app.get('/api/artifacts')
 def artifacts():return jsonify(build_summary()['artifacts'])
 @app.get('/')
 def index():return send_from_directory(app.static_folder,'index.html')
 return app
app=create_app()

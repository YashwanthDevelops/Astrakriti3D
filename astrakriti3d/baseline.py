"""Read-only Phase 5 baseline reconstruction and artifact inventory."""
from __future__ import annotations
import hashlib, json, mimetypes, platform, subprocess, sys, sqlite3, zipfile
from pathlib import Path

SCHEMA_VERSION="phase5.baseline.v1"
class BaselineError(RuntimeError): pass

def _sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def _version(cmd):
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
        return (p.stdout or p.stderr).splitlines()[0] if p.returncode==0 else None
    except Exception: return None

def _validate(path, name):
    p=Path(path); result={"status":"valid","checks":[]}
    data=p.read_bytes()
    if not data: return {"status":"invalid","checks":["empty file"]}
    if name.endswith('.json') or name.endswith('.geojson'):
        try:
            obj=json.loads(data.decode('utf-8')); result["checks"].append("json_parse")
            if name=='cameras.json':
                result["record_count"]=len(obj) if isinstance(obj,dict) else 0
                result["checks"].append("camera_metadata_object") if isinstance(obj,dict) else result.update(status="invalid")
            elif name=='shots.geojson':
                features=obj.get('features',[]) if isinstance(obj,dict) else []
                result["record_count"]=len(features)
                good=all(f.get('geometry',{}).get('type')=='Point' and len(f.get('geometry',{}).get('coordinates',[]))>=2 for f in features)
                result["checks"].append("point_coordinates") if good else result.update(status="invalid")
                result["crs"]="WGS84 longitude/latitude inferred from coordinate ranges; CRS member absent"
            return result
        except Exception as e: return {"status":"invalid","checks":[f"json_parse_error:{type(e).__name__}"]}
    if name.endswith('.pdf'):
        result["checks"].append("pdf_signature") if data.startswith(b'%PDF-') else result.update(status="invalid")
    elif name.endswith('.tif') or name.endswith('.tiff'):
        result["checks"].append("tiff_signature") if data[:4] in (b'II*\x00',b'MM\x00*') else result.update(status="invalid")
        result["crs"]="not read from TIFF tags by bundled validator"; result["units"]="unknown"
    elif name.endswith('.laz') or name.endswith('.las'):
        result["checks"].append("las_signature") if data[:4]==b'LASF' else result.update(status="invalid")
        result["crs"]="not read from LAS VLR by bundled validator"; result["units"]="unknown"; result["scale_verified"]=False
    elif name.endswith('.zip'):
        result["checks"].append("zip_members") if zipfile.is_zipfile(p) else result.update(status="invalid")
    elif name.endswith('.glb'):
        result["checks"].append("glb_signature") if data[:4]==b'glTF' else result.update(status="invalid")
    return result

def inventory_baseline(result_path, output, phase4_dir=None):
    rp=Path(result_path)
    if not rp.is_file(): raise BaselineError(f"result record does not exist: {rp}")
    result=json.loads(rp.read_text(encoding='utf-8'))
    if not result.get('ok'): raise BaselineError("result record is not completed")
    root=Path(phase4_dir) if phase4_dir else rp.parent
    artifact_paths=[]
    for item in result.get('artifacts',[]): artifact_paths.append(Path(item.get('path','')))
    if not artifact_paths:
        artifact_paths=[root/'artifacts'/x for x in ('orthophoto.tif','georeferenced_model.laz','shots.geojson','cameras.json','report.pdf')]
    artifacts=[]; missing=[]
    for p in artifact_paths:
        if not p.is_file(): missing.append(str(p)); continue
        name=p.name; actual=_sha(p); declared=next((x.get('sha256') for x in result.get('artifacts',[]) if x.get('name')==name or Path(x.get('path','')).name==name),None)
        validation=_validate(p,name); validation["hash_match"]=declared is None or declared==actual
        if not validation["hash_match"]: validation["status"]="invalid"
        artifacts.append({"name":name,"path":str(p.resolve()),"size_bytes":p.stat().st_size,"mime":mimetypes.guess_type(name)[0] or 'application/octet-stream',"sha256":actual,"declared_sha256":declared,"provenance":"downloaded from WebODM task","classification":"analytical" if name in ('orthophoto.tif','georeferenced_model.laz','shots.geojson') else 'viewer/report derivative',"crs":validation.get('crs','unknown'),'units':validation.get('units','unknown'),'axes':'unknown','metric_scale_verified':False,"validation":validation})
    events=result.get('events',[]); times=[e.get('timestamp') for e in events if e.get('timestamp')]
    timing={"event_count":len(events),"first_event":times[0] if times else None,"last_event":times[-1] if times else None,"inclusive_wall_seconds":None,"stage_events":{}}
    if len(times)>=2:
        from datetime import datetime
        try: timing["inclusive_wall_seconds"]=(datetime.fromisoformat(times[-1])-datetime.fromisoformat(times[0])).total_seconds()
        except ValueError: pass
    for e in events: timing["stage_events"].setdefault(e.get('status','unknown'),0); timing["stage_events"][e.get('status','unknown')]+=1
    # Poll events are the available timing boundary; sum intervals spent in
    # each reported state and disclose that this is polling-derived.
    from datetime import datetime
    stage_seconds={}
    for a,b in zip(events,events[1:]):
        try: stage_seconds[a.get('status','unknown')]=stage_seconds.get(a.get('status','unknown'),0)+(datetime.fromisoformat(b['timestamp'])-datetime.fromisoformat(a['timestamp'])).total_seconds()
        except (KeyError,TypeError,ValueError): pass
    timing["stage_seconds_polling_derived"]=stage_seconds
    project=Path(__file__).resolve().parents[1]
    prepared=project/'evidence'/'phase4'/'real-run'/'prepared_manifest.json'
    geo=project/'evidence'/'phase4'/'real-run'/'geo.txt'
    phase2_manifest=project/'evidence'/'phase2'/'real-run'/'manifest.json'
    association=project/'evidence'/'phase3'/'real-run'/'association_manifest.json'
    video=project/'inputs'/'DJI_0142.MP4'
    source_hashes={}
    for label,p in (("prepared_manifest",prepared),("geo_txt",geo)):
        if p.is_file(): source_hashes[label]={"path":str(p.resolve()),"sha256":_sha(p)}
    for label,p in (("phase2_manifest",phase2_manifest),("phase3_association_manifest",association),("source_video",video)):
        if p.is_file(): source_hashes[label]={"path":str(p.resolve()),"sha256":_sha(p)}
    persisted={}
    db=Path('runtime/jobs.sqlite3')
    if db.is_file() and result.get('local_job_id'):
        try:
            con=sqlite3.connect(db); row=con.execute('select project_id,task_id,options,state,created_at,updated_at from jobs where local_id=?',(result['local_job_id'],)).fetchone(); con.close()
            if row: persisted={"project_id":row[0],"task_id":row[1],"effective_options":json.loads(row[2]),"state":row[3],"created_at":row[4],"updated_at":row[5]}
        except Exception: persisted={}
    task={"local_job_id":result.get('local_job_id'),"project_id":result.get('project_id'),"task_id":result.get('task_id'),"fingerprint":result.get('fingerprint'),"effective_options":result.get('options',[]),"persistence":persisted,"webodm_version":"not present in saved task record","processing_engine_version":"not present in saved task record","nodeodx_version":"not present in saved task record"}
    if persisted: task.update({k:persisted[k] for k in ('project_id','task_id','effective_options')})
    report={"schema_version":SCHEMA_VERSION,"task":task,"sources":source_hashes,"environment":{"python":sys.version,"platform":platform.platform(),"ffmpeg":_version(['ffmpeg','-version']),"ffprobe":_version(['ffprobe','-version'])},"timing":timing,"artifacts":sorted(artifacts,key=lambda x:x['name']),"missing_artifacts":missing,"validation_summary":{"all_present":not missing,"all_hashes_match":all(x['validation']['hash_match'] for x in artifacts),"all_structurally_valid":all(x['validation']['status']=='valid' for x in artifacts),"metric_scale_verified":False,"accuracy_status":"unverified; no surveyed independent reference"},"limitations":["CRS, units and axes are unknown where not declared in artifact metadata.","Structural opening and signatures do not establish geometric correctness.","GPS/camera agreement and reconstructed appearance do not prove metric accuracy or scene completeness.","No independent survey/checkpoint reference was available.","WebODM, NodeODX and processing-engine versions were not included in the saved task record."],"reproducible":not missing and all(x['validation']['hash_match'] and x['validation']['status']=='valid' for x in artifacts)}
    out=Path(output); out.mkdir(parents=True,exist_ok=True); (out/'baseline_inventory.json').write_text(json.dumps(report,indent=2),encoding='utf-8'); return report

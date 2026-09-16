"""Failure-safe WebODM reconstruction execution and evidence preservation."""
from __future__ import annotations
import json, re, shutil, time, uuid
from datetime import datetime, timezone
from pathlib import Path

from .client import WebODMClient
from .config import Config
from .storage import manifest_for_images
from .preflight import run_preflight

def _now(): return datetime.now(timezone.utc).isoformat()
def _sha(path):
    import hashlib
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()
def _write(path, data): Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
def _append(path, data):
    with Path(path).open("a", encoding="utf-8") as fh: fh.write(json.dumps(data, default=str) + "\n")

def _classify_failure(stage, exit_code, text, service_error=False):
    low = (text or "").lower()
    if service_error or any(x in low for x in ("connection refused", "timeout", "nodeodm", "webodm api")): category = "service_failure"
    elif "texrecon" in low or "mvs_texturing" in low or str(exit_code) in {"3221225477", "0xc0000005"}: category = "texrecon"
    elif any(x in low for x in ("out of memory", "cannot allocate", "bad_alloc", "resource exhaustion")): category = "memory"
    elif any(x in low for x in ("alignment", "opensfm", "reconstruction failed", "not enough matches")): category = "alignment"
    elif any(x in low for x in ("geo.txt", "invalid coordinate", "missing image", "malformed", "input")): category = "invalid_input"
    elif stage in {"mvs_texturing", "texturing"}: category = "texrecon"
    else: category = "unknown_engine_failure"
    guidance = {"texrecon":["retry with preserved inputs","use the geometry-only/odm_meshing fallback","run a lower-resource diagnostic","investigate the installed texrecon/WebODM build"],"memory":["retry after closing heavy processes","use lower-resource diagnostic settings","increase pagefile or available RAM"],"invalid_input":["validate frame hashes and geo.txt","fix telemetry associations","submit a fresh unique run directory"],"alignment":["inspect frame overlap and coverage","retry with the same preserved dataset","keep R1 as fallback"],"service_failure":["restart WebODM/NodeODM","verify API authentication and queue health","retry from this preserved run directory"],"unknown_engine_failure":["inspect preserved API/processing logs","retry only after identifying the failing stage"]}
    return category, guidance[category]

def _stage(task, previous=None):
    value = task.get("running_stage") or task.get("stage") or task.get("processing_stage")
    if value: return str(value)
    error = str(task.get("last_error") or "")
    for name in ("dataset","opensfm","openmvs","odm_filterpoints","odm_meshing","mvs_texturing","odm_georeferencing","odm_orthophoto","odm_report","odm_postprocess"):
        if name.lower() in error.lower(): return name
    return previous or "unknown"

def _artifact_inventory(run_dir):
    out=[]
    for p in sorted(Path(run_dir).rglob("*")):
        if p.is_file() and p.name not in {"api_log.jsonl","processing_log.jsonl"}:
            out.append({"path":str(p.relative_to(run_dir)),"size_bytes":p.stat().st_size,"sha256":_sha(p)})
    return out

def _failure_report(run_dir, stage, exit_code, text, service_error=False, cancelled=False):
    category, guidance = _classify_failure(stage, exit_code, text, service_error)
    partial = _artifact_inventory(run_dir)
    report={"schema_version":"astrakriti3d.recovery-failure.v1","status":"cancelled" if cancelled else "failed","failure_stage":stage,"exit_code":exit_code,"native_process":"texrecon" if category=="texrecon" else None,"category":"cancellation" if cancelled else category,"partial_outputs":partial,"partial_output_count":len(partial),"guidance":["preserve this run directory"] + (["safe cancellation was requested; no prior artifacts were removed"] if cancelled else guidance),"diagnostic_text":text[-10000:] if text else None}
    _write(Path(run_dir)/"failure_report.json",report)
    lines=["# Reconstruction failure report","",f"Status: **{report['status'].upper()}**",f"Category: `{report['category']}`",f"Stage: `{stage}`",f"Exit code: `{exit_code}`",f"Native process: `{report['native_process'] or 'not identified'}`","","## Recovery guidance",""]+[f"- {x}" for x in report["guidance"]]+["",f"Partial outputs preserved: **{len(partial)}**","","All source inputs and prior artifacts were left untouched."]
    (Path(run_dir)/"failure_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return report

def _save_processing_output(client, project_id, task_id, run_dir, api_log):
    if not project_id or not task_id: return
    try:
        (Path(run_dir) / "webodm_output.log").write_text(client.output(project_id, task_id), encoding="utf-8")
        _append(api_log, {"timestamp": _now(), "operation": "output", "status": "passed"})
    except Exception as exc:
        _append(api_log, {"timestamp": _now(), "operation": "output", "error": str(exc)})

def run_reconstruction(video, images, output, *, mode, srt=None, geo_txt=None, selector_config=None, options=None, config=None, preflight_runner=run_preflight, client_factory=WebODMClient, poll_seconds=3.0, cancel_after=None):
    if mode not in {"local","georeferenced"}: raise ValueError("mode must be local or georeferenced")
    if mode=="local" and geo_txt: raise ValueError("local reconstruction must omit geo.txt")
    if mode=="georeferenced" and (not srt or not geo_txt): raise ValueError("georeferenced reconstruction requires --srt and --geo-txt")
    base=Path(output).resolve(); base.mkdir(parents=True,exist_ok=True)
    run_dir=base/f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:10]}"; run_dir.mkdir()
    image_manifest=manifest_for_images(images); copied_geo=None
    if geo_txt: copied_geo=run_dir/"geo.txt"; shutil.copy2(geo_txt,copied_geo)
    selector_data=None
    if selector_config: selector_data=json.loads(Path(selector_config).read_text(encoding="utf-8")); shutil.copy2(selector_config,run_dir/"selector_config.json")
    _write(run_dir/"selected_frame_manifest.json",{"mode":mode,"images":image_manifest})
    preflight=preflight_runner(video,run_dir/"preflight",mode=mode,srt=srt,config=config or Config.from_env())
    run_manifest={"schema_version":"astrakriti3d.reconstruction-run.v1","run_id":run_dir.name,"created_at":_now(),"mode":mode,"video":{"path":str(Path(video).resolve()),"sha256":_sha(video)},"images":image_manifest,"geo_txt":{"path":str(copied_geo),"sha256":_sha(copied_geo)} if copied_geo else None,"selector_config":selector_data,"webodm_options":options or [],"preflight_status":preflight.get("status"),"preflight":preflight}
    _write(run_dir/"run_manifest.json",run_manifest)
    status={"status":"preflight_failed" if preflight.get("status")!="PASS" else "ready","mode":mode,"run_id":run_dir.name,"stage":"preflight","events":[],"terminal":False}; _write(run_dir/"task_status.json",status)
    if preflight.get("status")!="PASS":
        report=_failure_report(run_dir,"preflight",None,"preflight failed; submission was prevented"); status.update({"status":"preflight_failed","terminal":True}); _write(run_dir/"task_status.json",status); return {"ok":False,"run_dir":str(run_dir),"run_manifest":run_manifest,"task_status":status,"failure_report":report}
    client=client_factory(config or Config.from_env()); api_log=run_dir/"api_log.jsonl"; processing_log=run_dir/"processing_log.jsonl"; task=None; task_id=None; project_id=None; previous_stage="preflight"; started=time.monotonic()
    try:
        _append(api_log,{"timestamp":_now(),"operation":"authenticate"}); client.authenticate(); _append(api_log,{"timestamp":_now(),"operation":"authenticate","status":"passed"})
        _append(api_log,{"timestamp":_now(),"operation":"find_or_create_project"}); project_id=client.find_or_create_project(); _append(api_log,{"timestamp":_now(),"operation":"find_or_create_project","project_id":project_id})
        _append(api_log,{"timestamp":_now(),"operation":"submit_task","mode":mode,"geo_included":bool(copied_geo)}); task_id=client.submit_task(project_id,image_manifest,options or [],geo_txt=copied_geo if mode=="georeferenced" else None); _append(api_log,{"timestamp":_now(),"operation":"submit_task","task_id":task_id,"project_id":project_id})
        run_manifest.update({"project_id":project_id,"task_id":task_id}); _write(run_dir/"run_manifest.json",run_manifest); status.update({"status":"submitted","task_id":task_id,"project_id":project_id}); _write(run_dir/"task_status.json",status)
        while True:
            if cancel_after is not None and time.monotonic()-started>=cancel_after:
                _append(api_log,{"timestamp":_now(),"operation":"cancel_task","task_id":task_id}); client.cancel(project_id,task_id); status.update({"status":"cancelled","terminal":True}); _write(run_dir/"task_status.json",status); report=_failure_report(run_dir,previous_stage,None,"safe cancellation requested",cancelled=True); return {"ok":False,"run_dir":str(run_dir),"task_id":task_id,"failure_report":report}
            try: task=client.task(project_id,task_id); _append(api_log,{"timestamp":_now(),"operation":"poll_task","task_id":task_id,"status":task.get("status")})
            except Exception as exc:
                _append(api_log,{"timestamp":_now(),"operation":"poll_task","error":str(exc)}); _save_processing_output(client,project_id,task_id,run_dir,api_log); report=_failure_report(run_dir,previous_stage,None,str(exc),service_error=True); status.update({"status":"service_failure","terminal":True}); _write(run_dir/"task_status.json",status); return {"ok":False,"run_dir":str(run_dir),"task_id":task_id,"failure_report":report}
            stage=_stage(task,previous_stage); event={"timestamp":_now(),"stage":stage,"status":task.get("status"),"progress":task.get("running_progress",task.get("upload_progress")),"last_error":task.get("last_error")}; _append(processing_log,event); status["events"].append(event); status.update({"status":task.get("status"),"stage":stage}); _write(run_dir/"task_status.json",status); previous_stage=stage
            raw_value=task.get("status")
            if raw_value is None:
                # WebODM can briefly return a task record without status just
                # after upload. Preserve the event and poll again instead of
                # converting None to int and falsely failing the run.
                time.sleep(poll_seconds)
                continue
            raw=int(raw_value)
            if raw==40:
                for asset in task.get("available_assets",[]):
                    try: client.download(project_id,task_id,asset,run_dir/"artifacts"/asset); _append(api_log,{"timestamp":_now(),"operation":"download","asset":asset,"status":"passed"})
                    except Exception as exc: _append(api_log,{"timestamp":_now(),"operation":"download","asset":asset,"error":str(exc)})
                try: (run_dir/"webodm_output.log").write_text(client.output(project_id,task_id),encoding="utf-8")
                except Exception as exc: _append(api_log,{"timestamp":_now(),"operation":"output","error":str(exc)})
                artifacts=_artifact_inventory(run_dir)
                if not any(x["path"].endswith("shots.geojson") for x in artifacts):
                    report=_failure_report(run_dir,stage,None,"task reached completed status but required camera output was absent"); status.update({"status":"partial_output","terminal":True}); _write(run_dir/"task_status.json",status); return {"ok":False,"run_dir":str(run_dir),"task_id":task_id,"failure_report":report}
                status.update({"status":"completed","terminal":True,"artifacts":artifacts}); _write(run_dir/"task_status.json",status); return {"ok":True,"run_dir":str(run_dir),"task_id":task_id,"artifacts":artifacts}
            if raw in {30,50}:
                text=str(task.get("last_error") or ""); match=re.search(r"(?:exit(?: code)?|returned)\D+(0x[0-9a-fA-F]+|\d+)",text,re.I); code=match.group(1) if match else None; _save_processing_output(client,project_id,task_id,run_dir,api_log); report=_failure_report(run_dir,stage,code,text,cancelled=raw==50); status.update({"status":"failed" if raw==30 else "cancelled","terminal":True}); _write(run_dir/"task_status.json",status); return {"ok":False,"run_dir":str(run_dir),"task_id":task_id,"failure_report":report}
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        if project_id and task_id:
            try: client.cancel(project_id,task_id)
            except Exception: pass
        _save_processing_output(client,project_id,task_id,run_dir,api_log); report=_failure_report(run_dir,previous_stage,None,"keyboard interruption; cancellation attempted",cancelled=True); status.update({"status":"cancelled","terminal":True}); _write(run_dir/"task_status.json",status); return {"ok":False,"run_dir":str(run_dir),"task_id":task_id,"failure_report":report}
    except Exception as exc:
        _save_processing_output(client,project_id,task_id,run_dir,api_log); report=_failure_report(run_dir,previous_stage,None,str(exc),service_error=True); status.update({"status":"failed","terminal":True}); _write(run_dir/"task_status.json",status); return {"ok":False,"run_dir":str(run_dir),"task_id":task_id,"failure_report":report}

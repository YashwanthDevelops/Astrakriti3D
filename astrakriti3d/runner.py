import hashlib, json, time, uuid
from pathlib import Path
from .storage import JobStore, manifest_for_images, fingerprint, preflight_report, now

STATUS={10:"queued",20:"running",30:"failed",40:"completed",50:"cancelled"}
def run(config, images, output, options=None, cancel_after=None, client=None, geo_txt=None, mode=None):
    if mode not in (None, "local", "georeferenced"):
        return {"schema_version":"1.0", "ok":False, "error":{"type":"ValueError","message":"mode must be local or georeferenced"}}
    if mode == "local" and geo_txt:
        return {"schema_version":"1.0", "ok":False, "mode":"local", "error":{"type":"ValueError","message":"local mode must omit geo.txt/GCP inputs"}}
    if mode == "georeferenced" and not geo_txt:
        return {"schema_version":"1.0", "ok":False, "mode":"georeferenced", "error":{"type":"ValueError","message":"georeferenced mode requires geo.txt"}}
    options=options or []; store=JobStore(config.db_path)
    try: manifest=manifest_for_images(images)
    except Exception as e: return {"schema_version":"1.0","ok":False,"error":{"type":"ValueError","message":str(e)}}
    if mode != "local" and not geo_txt:
        p_img=Path(images)
        if (p_img/"geo.txt").is_file(): geo_txt=str(p_img/"geo.txt")
        elif (p_img.parent/"geo.txt").is_file(): geo_txt=str(p_img.parent/"geo.txt")
    geo_sha=__import__('hashlib').sha256(Path(geo_txt).read_bytes()).hexdigest() if geo_txt else None
    fp=fingerprint(manifest,options,geo_sha); existing=store.get_by_fingerprint(fp) or (None if geo_txt else store.find_by_manifest(manifest,options))
    local_id=existing["local_id"] if existing else str(uuid.uuid4())
    if not existing: store.create(local_id,fp,manifest,options)
    report=preflight_report(manifest); Path(output).mkdir(parents=True,exist_ok=True); (Path(output)/"preflight.json").write_text(json.dumps(report,indent=2))
    effective_mode = mode or ("georeferenced" if geo_txt else "local")
    result={"schema_version":"1.0","ok":False,"mode":effective_mode,"local_job_id":local_id,"fingerprint":fp,"events":[],"preflight":report}
    try:
        config.validate(); client=client or __import__("astrakriti3d.client",fromlist=["WebODMClient"]).WebODMClient(config); client.authenticate(); result["authenticated"]=True
        project_id=existing["project_id"] if existing and existing["project_id"] else client.find_or_create_project(); store.update(local_id,project_id=project_id,state="submitted")
        if existing and existing["task_id"]: task_id=existing["task_id"]
        else: task_id=client.submit_task(project_id,manifest,options,geo_txt=geo_txt) if geo_txt else client.submit_task(project_id,manifest,options)
        store.update(local_id,task_id=task_id)
        start=time.monotonic()
        unknown=0; started=time.monotonic()
        while True:
            try: task=client.task(project_id,task_id)
            except Exception as e:
                unknown += 1; event={"timestamp":now(),"status":"transient_error","retry_count":unknown,"next_action":"retry_poll","summary":str(e)[:300]}; result["events"].append(event); store.event(local_id,event)
                if unknown >= config.max_unknown_polls or time.monotonic()-started >= config.max_poll_seconds: raise RuntimeError("polling retry policy exhausted")
                time.sleep(config.poll_interval); continue
            raw_status=task.get("status");
            if raw_status is None:
                unknown += 1; event={"timestamp":now(),"status":"unknown","retry_count":unknown,"next_action":"retry_poll","summary":{k:task.get(k) for k in ("id","last_error","upload_progress","running_progress")}}; result["events"].append(event); store.event(local_id,event)
                if unknown >= config.max_unknown_polls or time.monotonic()-started >= config.max_poll_seconds: raise RuntimeError("unknown WebODM status retry policy exhausted")
                time.sleep(config.poll_interval); continue
            try: status=int(raw_status)
            except (TypeError,ValueError):
                unknown += 1; event={"timestamp":now(),"status":"unknown","retry_count":unknown,"next_action":"retry_poll","summary":str(raw_status)[:100]}; result["events"].append(event); store.event(local_id,event)
                if unknown >= config.max_unknown_polls or time.monotonic()-started >= config.max_poll_seconds: raise RuntimeError("invalid WebODM status retry policy exhausted")
                time.sleep(config.poll_interval); continue
            unknown=0; progress=task.get("running_progress",task.get("upload_progress",0)); event={"timestamp":now(),"status":STATUS.get(status,"unknown"),"progress":progress,"raw_status":status}; result["events"].append(event); store.event(local_id,event); store.update(local_id,state={10:"submitted",20:"running",30:"failed",40:"collecting",50:"cancelled"}.get(status,"running"),progress=float(progress or 0),diagnostics=task.get("last_error"))
            if cancel_after is not None and time.monotonic()-start>=cancel_after and status not in {30,40,50}: client.cancel(project_id,task_id); store.update(local_id,state="cancelled"); result["cancelled"]=True; result["ok"]=False; break
            if status==30: raise RuntimeError(task.get("last_error") or "remote task failed")
            if status==50: result["cancelled"]=True; break
            if status==40:
                artifacts=[]
                dest=Path(output)/"artifacts"/"orthophoto.tif"
                try:
                    client.download(project_id,task_id,"orthophoto.tif",dest)
                    digest=hashlib.sha256(dest.read_bytes()).hexdigest()
                    artifacts.append({"name":"orthophoto.tif","path":str(dest),"sha256":digest})
                    result["artifact"]={"path":str(dest),"sha256":digest}
                except Exception: pass
                for asset in ("shots.geojson","cameras.json","report.pdf","georeferenced_model.laz","textured_model.zip","textured_model.glb"):
                    if asset in task.get("available_assets",[]):
                        try:
                            adest=Path(output)/"artifacts"/asset
                            client.download(project_id,task_id,asset,adest)
                            adigest=hashlib.sha256(adest.read_bytes()).hexdigest()
                            artifacts.append({"name":asset,"path":str(adest),"sha256":adigest})
                        except Exception: pass
                shots_file=Path(output)/"artifacts"/"shots.geojson"
                if shots_file.is_file():
                    try:
                        sdata=json.loads(shots_file.read_text(encoding="utf-8"))
                        cams={f["properties"]["filename"]:f["geometry"]["coordinates"] for f in sdata.get("features",[]) if f.get("properties",{}).get("filename") and f.get("geometry",{}).get("coordinates")}
                        result["camera_coordinates"]=cams
                        result["camera_count"]=len(cams)
                    except Exception: pass
                store.update(local_id,state="completed",artifacts=artifacts)
                result.update({"ok":True,"artifacts":artifacts})
                break
            time.sleep(config.poll_interval)
        result.update({"project_id":project_id,"task_id":task_id}); return result
    except Exception as e:
        store.update(local_id,state="failed",diagnostics={"error":str(e)}); result["error"]={"type":type(e).__name__,"message":str(e)}
        if 'project_id' in locals(): result['project_id']=project_id
        if 'task_id' in locals(): result['task_id']=task_id
        return result

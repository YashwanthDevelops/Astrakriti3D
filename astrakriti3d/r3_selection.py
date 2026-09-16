"""Experimental R3 AI-assisted selector with deterministic R1 fallback.

The learned component is optional and must be a caller-supplied TorchScript
model. No weights are downloaded. If loading, inference, or safety validation
fails, all input frames are selected.
"""
from __future__ import annotations
import hashlib, json, shutil, os, time
from pathlib import Path

SCHEMA_VERSION = "phase6.r3-selection.v1"

class R3SelectionError(RuntimeError): pass
def _sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def _manifest_hash(p): return _sha(p)

def _load_model(model_path, device):
    import torch
    model = torch.jit.load(str(model_path), map_location=device)
    model.eval()
    return model

def _embedding(model, image_path, device):
    from PIL import Image
    import torch
    import numpy as np
    with Image.open(image_path) as im:
        im = im.convert("RGB").resize((224, 224))
        arr = np.asarray(im, dtype=np.float32) / 255.0
    x = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)
    x = (x - 0.5) / 0.5
    with torch.inference_mode():
        y = model(x.to(device))
    if isinstance(y, (tuple, list)): y = y[0]
    y = y.detach().float().reshape(-1).cpu().numpy()
    norm = float(np.linalg.norm(y))
    if not norm or not np.isfinite(norm): raise R3SelectionError("model returned invalid embedding")
    return (y / norm).tolist()

def _cosine(a, b): return sum(x*y for x,y in zip(a,b))

def select_r3(manifest_path, frames_dir, output, geo_txt=None, model_path=None,
              device="cpu", similarity_threshold=0.995, max_gap_seconds=2.0):
    manifest_path, frames_dir, out = map(Path, (manifest_path, frames_dir, output))
    data = json.loads(manifest_path.read_text(encoding="utf-8")); frames=data.get("frames",[])
    if not frames: raise R3SelectionError("manifest contains no frames")
    names=[f.get("output_filename") for f in frames]
    if len(set(names)) != len(names) or any(not n for n in names): raise R3SelectionError("invalid frame identities")
    for f in frames:
        p=Path(f.get("output_path") or frames_dir/f["output_filename"])
        if not p.is_file(): raise R3SelectionError(f"missing frame: {p}")
        if f.get("sha256") and _sha(p) != f["sha256"]: raise R3SelectionError(f"hash mismatch: {p.name}")
    fallback=None; model_meta={"path":None,"backend":"unavailable","device":device}; pair_metrics=[]; learned_scores=None; vectors=None
    out.mkdir(parents=True,exist_ok=True)
    progress_path=out/"progress.jsonl"; progress_path.write_text("",encoding="utf-8")
    def progress(event):
        with progress_path.open("a",encoding="utf-8") as fh:
            fh.write(json.dumps({"timestamp":time.time(),**event},sort_keys=True)+"\n")
    try:
        if model_path is None: raise R3SelectionError("no frozen TorchScript model supplied")
        if str(model_path).lower().endswith('.pth'):
            from .lightglue_adapter import LightGlueSiftAdapter
            adapter=LightGlueSiftAdapter(model_path, Path(model_path).parent, device=device)
            pair_metrics=[None]
            progress({"event":"model_loaded","model":adapter.metadata})
            for pair_index,(left,right) in enumerate(zip(frames,frames[1:]),start=1):
                lp=Path(left.get("output_path") or frames_dir/left["output_filename"]); rp=Path(right.get("output_path") or frames_dir/right["output_filename"])
                metric=adapter.pair_metrics(lp,rp); pair_metrics.append(metric)
                rss=None
                try:
                    import psutil; rss=psutil.Process(os.getpid()).memory_info().rss
                except Exception: pass
                progress({"event":"pair_complete","pair_index":pair_index,"total_pairs":len(frames)-1,"first":left["output_filename"],"second":right["output_filename"],"metric":metric,"rss_bytes":rss})
            model_meta={**adapter.metadata,"backend":"lightglue_sift"}; learned_scores=[None]+[x["overlap_score"] for x in pair_metrics[1:]]
        else:
            import torch
            model=_load_model(model_path, device); model_meta={"path":str(Path(model_path).resolve()),"sha256":_sha(model_path),"backend":"torchscript","torch":torch.__version__,"device":device}
            vectors=[]
            for f in frames: vectors.append(_embedding(model, Path(f.get("output_path") or frames_dir/f["output_filename"]), device))
    except Exception as exc:
        fallback=str(exc); vectors=None; progress({"event":"selector_error","error":fallback})
    selected=[]; diagnostics=[]; last_ts=None; prev_vec=None
    for i,f in enumerate(frames):
        p=Path(f.get("output_path") or frames_dir/f["output_filename"]); ts=float(f.get("source_timestamp_seconds",0)); reasons=[]; keep=True; sim=None
        if i in (0,len(frames)-1): reasons.append("endpoint_protected")
        if last_ts is None or ts-last_ts >= max_gap_seconds: reasons.append("temporal_continuity_protected")
        if learned_scores is not None: sim=learned_scores[i]
        elif vectors is not None and prev_vec is not None: sim=_cosine(vectors[i],prev_vec)
        if (learned_scores is not None or vectors is not None) and not reasons and sim is not None and sim >= similarity_threshold: keep=False; reasons=["learned_visual_redundancy"]
        if vectors is None: keep=True; reasons=["learned_fallback_all_frames"]
        if keep:
            dest=out/"frames"/p.name; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dest); selected.append({"output_filename":p.name,"source_sha256":f.get("sha256") or _sha(p),"sha256":_sha(dest),"source_timestamp_seconds":f.get("source_timestamp_seconds"),"source_frame_index":f.get("source_frame_index")}); last_ts=ts
        diagnostics.append({"output_filename":p.name,"decision":"keep" if keep else "reject","reasons":reasons,"learned_similarity":sim,"source_sha256":f.get("sha256") or _sha(p)})
        if vectors is not None and keep: prev_vec=vectors[i]
    # Safety: an optional scorer may not reduce below protected temporal coverage.
    if selected and any(float(b["source_timestamp_seconds"])-float(a["source_timestamp_seconds"]) > max_gap_seconds for a,b in zip(selected,selected[1:])):
        fallback="unsafe temporal gap"; selected=[]
        for f in frames:
            p=Path(f.get("output_path") or frames_dir/f["output_filename"]); dest=out/"frames"/p.name; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dest); selected.append({"output_filename":p.name,"source_sha256":f.get("sha256") or _sha(p),"sha256":_sha(dest),"source_timestamp_seconds":f.get("source_timestamp_seconds"),"source_frame_index":f.get("source_frame_index")})
        diagnostics=[{"output_filename":f["output_filename"],"decision":"keep","reasons":["learned_fallback_all_frames","unsafe_gap_recovery"],"source_sha256":f.get("sha256") or _sha(Path(f.get("output_path") or frames_dir/f["output_filename"]))} for f in frames]
    selected_names={x["output_filename"] for x in selected}; geo_out=None; geo_alignment=None
    if geo_txt:
        lines=Path(geo_txt).read_text(encoding="utf-8").splitlines()
        if not lines or lines[0] != "EPSG:4326": raise R3SelectionError("geo.txt must begin with EPSG:4326")
        records=[x for x in lines[1:] if x.split() and x.split()[0] in selected_names]
        if len(records)!=len(selected): raise R3SelectionError("geo.txt does not exactly cover selected frames")
        geo_out=out/"geo.txt"; geo_out.write_text("\n".join([lines[0]]+records)+"\n",encoding="utf-8")
        geo_alignment={"selected_count":len(selected),"geo_record_count":len(records),"sha256":_sha(geo_out),"names_match":{x.split()[0] for x in records}==selected_names}
    report={"schema_version":SCHEMA_VERSION,"arm":"R3","production_baseline":"R1","fallback":fallback,"model":model_meta,"preprocessing":{"size":[224,224],"normalization":"adapter-specific; official LightGlue load_image for SIFT"},"thresholds":{"similarity":similarity_threshold,"max_gap_seconds":max_gap_seconds},"pair_window":1,"source_manifest_sha256":_manifest_hash(manifest_path),"candidate_count":len(frames),"selected_count":len(selected),"rejected_count":len(frames)-len(selected),"frames":selected,"diagnostics":diagnostics,"pair_metrics":pair_metrics,"geo_alignment":geo_alignment,"deterministic":True,"ai_accuracy_claim":False}
    out.mkdir(parents=True,exist_ok=True); (out/"selection_manifest.json").write_text(json.dumps(report,indent=2,sort_keys=True),encoding="utf-8"); (out/"determinism.json").write_text(json.dumps({"manifest_sha256":_sha(out/"selection_manifest.json"),"model":model_meta,"fallback":fallback},indent=2,sort_keys=True),encoding="utf-8")
    return report

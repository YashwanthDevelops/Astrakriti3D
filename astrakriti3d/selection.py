"""Transparent, deterministic classical R1/R2 frame-selection experiment."""
from __future__ import annotations
import hashlib, json, shutil, time, csv, math
from pathlib import Path

SCHEMA_VERSION="phase6.selection.v1"
class SelectionError(RuntimeError): pass

def _sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

ADAPTIVE_DEFAULTS = {
    "target_fps": 2.0, "min_feature_displacement": 12.0,
    "min_new_feature_ratio": 0.20, "min_useful_matches": 80,
    "min_features": 150, "max_gap_seconds": 2.0,
    "min_blur": 10.0, "max_clipped_ratio": 0.15,
    "proxy_width": 960,
}

def _adaptive_metrics(path, previous=None, previous_features=None, cfg=None):
    """Return deterministic proxy metrics for one image and its predecessor."""
    import cv2, numpy as np
    cfg = {**ADAPTIVE_DEFAULTS, **(cfg or {})}
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None: raise SelectionError(f"image decode failed: {path}")
    h, w = image.shape[:2]; scale = cfg["proxy_width"] / max(w, 1)
    proxy = cv2.resize(image, (cfg["proxy_width"], max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    blur = float(cv2.Laplacian(proxy, cv2.CV_64F).var())
    clipped = float(np.mean((proxy <= 3) | (proxy >= 252)))
    detector = cv2.SIFT_create(nfeatures=1000) if hasattr(cv2, "SIFT_create") else cv2.ORB_create(nfeatures=1000)
    keypoints, descriptors = detector.detectAndCompute(proxy, None)
    features = len(keypoints or [])
    useful = 0; ratio = 0.0; displacement = 0.0; new_ratio = 1.0; similarity = 0.0
    if previous is not None and previous_features is not None and descriptors is not None and previous_features[1] is not None:
        matcher = cv2.BFMatcher(cv2.NORM_L2 if hasattr(cv2, "SIFT_create") else cv2.NORM_HAMMING)
        pairs = matcher.knnMatch(previous_features[1], descriptors, k=2)
        good = [m for m, n in pairs if m.distance < 0.75 * n.distance]
        useful = len(good); ratio = useful / max(1, min(len(previous_features[0]), features))
        if good:
            shifts = [math.hypot(keypoints[m.trainIdx].pt[0] - previous_features[0][m.queryIdx].pt[0], keypoints[m.trainIdx].pt[1] - previous_features[0][m.queryIdx].pt[1]) for m in good]
            displacement = float(np.median(shifts))
        matched = {m.trainIdx for m in good}; new_ratio = max(0.0, (features - len(matched)) / max(1, features))
        similarity = max(0.0, 1.0 - displacement / max(1.0, cfg["proxy_width"]))
    return {"blur_score": blur, "clipped_ratio": clipped, "feature_count": features,
            "useful_match_count": useful, "match_ratio": ratio,
            "median_feature_displacement": displacement, "new_feature_ratio": new_ratio,
            "image_similarity": similarity}, (keypoints or [], descriptors), proxy

def adaptive_select_frames(manifest_path, frames_dir, output, **options):
    """Select geometry-useful frames without mutating the candidate pool."""
    cfg = {**ADAPTIVE_DEFAULTS, **{k: v for k, v in options.items() if v is not None}}
    if cfg["target_fps"] <= 0 or cfg["max_gap_seconds"] <= 0: raise SelectionError("target_fps and max_gap_seconds must be positive")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8")); frames = manifest.get("frames", [])
    if not frames: raise SelectionError("manifest contains no frames")
    out = Path(output); selected_dir = out / "frames"
    report_path = Path(options.get("selection_report") or out / "adaptive_selection.json")
    rows=[]; selected=[]; last_kept_ts=None; last_metrics=None; last_features=None; protected=0
    candidate_step=1.0 / cfg["target_fps"]; next_candidate=0.0
    for index, frame in enumerate(frames):
        ts=float(frame.get("source_timestamp_seconds", 0)); src=Path(frame.get("output_path") or Path(frames_dir)/frame["output_filename"])
        if ts + 1e-9 < next_candidate and index not in (0, len(frames)-1): continue
        while next_candidate <= ts + 1e-9: next_candidate += candidate_step
        metrics, features, _ = _adaptive_metrics(src, last_metrics, last_features, cfg)
        gap = None if last_kept_ts is None else ts-last_kept_ts
        endpoint = index in (0, len(frames)-1); continuity = last_kept_ts is None or gap >= cfg["max_gap_seconds"]
        usable = metrics["feature_count"] >= cfg["min_features"] and metrics["useful_match_count"] >= cfg["min_useful_matches"] and metrics["blur_score"] >= cfg["min_blur"] and metrics["clipped_ratio"] <= cfg["max_clipped_ratio"]
        geometric = metrics["median_feature_displacement"] >= cfg["min_feature_displacement"] or metrics["new_feature_ratio"] >= cfg["min_new_feature_ratio"]
        keep = endpoint or continuity or geometric or not usable
        reason = "endpoint_protected" if endpoint else "temporal_continuity_protected" if continuity else "useful_geometry" if geometric else "quality_or_support_uncertain" if not usable else "redundant_frame"
        if keep:
            selected.append({"output_filename":frame["output_filename"],"source_sha256":frame.get("sha256") or _sha(src),"sha256":_sha(src),"source_timestamp_seconds":ts,"source_frame_index":frame.get("source_frame_index")})
            last_kept_ts=ts; last_metrics=src; last_features=features
            if endpoint or continuity: protected += 1
        rows.append({"frame_number":index+1,"timestamp":ts,"source_path":str(src.resolve()),**metrics,"gps_distance":None,"time_since_last_kept":gap,"decision":"keep" if keep else "reject","rejection_reason":None if keep else reason})
    if not options.get("dry_run"):
        selected_dir.mkdir(parents=True, exist_ok=True)
        for item in selected: shutil.copy2(Path(item["source_sha256"] and next(f.get("output_path") or Path(frames_dir)/f["output_filename"] for f in frames if f["output_filename"]==item["output_filename"])), selected_dir/item["output_filename"])
    report={"schema_version":"phase6.adaptive-selection.v1","mode":"adaptive","configuration":cfg,"candidate_count":len(rows),"selected_count":len(selected),"rejected_count":len(rows)-len(selected),"frames":selected,"rows":rows,"dry_run":bool(options.get("dry_run")),"endpoint_and_continuity_protected":protected,"deterministic":True}
    report_path.parent.mkdir(parents=True,exist_ok=True); report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    with report_path.with_suffix(".csv").open("w",newline="",encoding="utf-8") as fh:
        if rows:
            writer=csv.DictWriter(fh,fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    return report

def _diagnostic(path, previous=None, use_features=True):
    try:
        import cv2, numpy as np
        image=cv2.imread(str(path),cv2.IMREAD_GRAYSCALE)
        if image is None: raise ValueError('image decode failed')
        proxy=cv2.resize(image,(320,180),interpolation=cv2.INTER_AREA)
        blur=float(cv2.Laplacian(proxy,cv2.CV_64F).var())
        difference=None if previous is None else float(np.mean(np.abs(proxy.astype(np.float32)-previous.astype(np.float32))))
        features=0; matches=None
        if use_features:
            orb=cv2.ORB_create(nfeatures=500); kp,des=orb.detectAndCompute(proxy,None); features=len(kp)
            if previous is not None:
                pk,pd=orb.detectAndCompute(previous,None)
                if des is not None and pd is not None:
                    ms=cv2.BFMatcher(cv2.NORM_HAMMING,crossCheck=True).match(des,pd); matches=len(ms)
        return {"blur_laplacian_variance":blur,"proxy_mean_absolute_difference":difference,"feature_count":features,"local_match_count":matches,"diagnostics_status":"measured","proxy_dimensions":[320,180]},proxy
    except Exception as e:
        return {"blur_laplacian_variance":None,"proxy_mean_absolute_difference":None,"feature_count":None,"local_match_count":None,"diagnostics_status":"uncertain","warning":str(e)},None

def select_frames(manifest_path, frames_dir, output, min_blur=10.0, duplicate_threshold=1.5, continuity_seconds=2.0, feature_floor=20):
    if min_blur<0 or duplicate_threshold<0 or continuity_seconds<=0 or feature_floor<0: raise SelectionError('thresholds must be non-negative and continuity_seconds must be positive')
    manifest=json.loads(Path(manifest_path).read_text(encoding='utf-8')); frames=manifest.get('frames',[])
    if not frames: raise SelectionError('manifest contains no frames')
    names=[f.get('output_filename') for f in frames]
    if any(not n for n in names) or len(set(names)) != len(names): raise SelectionError('manifest frame names must be present and unique')
    if any(frames[i].get('source_timestamp_seconds', 0) > frames[i+1].get('source_timestamp_seconds', 0) for i in range(len(frames)-1)): raise SelectionError('manifest timestamps must be monotonic')
    out=Path(output); selected_dir=out/'frames'; selected_dir.mkdir(parents=True,exist_ok=True)
    selected=[]; diagnostics=[]; previous=None; last_kept_time=None; started=time.monotonic()
    for i,frame in enumerate(frames):
        src=Path(frame.get('output_path') or Path(frames_dir)/frame['output_filename'])
        if not src.is_file(): raise SelectionError(f'missing source frame: {src}')
        if frame.get('sha256') and _sha(src)!=frame['sha256']: raise SelectionError(f'source frame hash mismatch: {src.name}')
        diag,proxy=_diagnostic(src,previous)
        ts=float(frame.get('source_timestamp_seconds',0)); reasons=[]; keep=True
        if i==0 or i==len(frames)-1: reasons.append('endpoint_protected')
        if last_kept_time is None or ts-last_kept_time>=continuity_seconds: reasons.append('temporal_continuity_protected')
        if diag['proxy_mean_absolute_difference'] is None or diag['proxy_mean_absolute_difference']>duplicate_threshold: reasons.append('viewpoint_change_or_uncertain')
        if diag['blur_laplacian_variance'] is None or diag['blur_laplacian_variance']>=min_blur: reasons.append('focus_acceptable_or_uncertain')
        if diag['feature_count'] is None or diag['feature_count']>=feature_floor: reasons.append('feature_support_or_uncertain')
        # Reject only a clearly redundant frame with adequate local support.
        clearly_duplicate=(diag['proxy_mean_absolute_difference'] is not None and diag['proxy_mean_absolute_difference']<=duplicate_threshold and diag['blur_laplacian_variance'] is not None and diag['blur_laplacian_variance']>=min_blur and diag['feature_count'] is not None and diag['feature_count']>=feature_floor and not any(x in reasons for x in ('endpoint_protected','temporal_continuity_protected','viewpoint_change_or_uncertain')))
        if clearly_duplicate: keep=False; reasons=['confirmed_local_redundancy']
        if keep:
            dest=selected_dir/frame['output_filename']; shutil.copy2(src,dest); selected.append({"output_filename":frame['output_filename'],"output_path":str(dest.resolve()),"source_timestamp_seconds":frame.get('source_timestamp_seconds'),"source_frame_index":frame.get('source_frame_index'),"sha256":_sha(dest),"source_sha256":frame.get('sha256')}); last_kept_time=ts
        diagnostics.append({"output_filename":frame['output_filename'],"source_sha256":frame.get('sha256'),"diagnostics":diag,"decision":"keep" if keep else "reject","reason":reasons})
        previous=proxy if proxy is not None else previous
    config={"min_blur_laplacian_variance":min_blur,"duplicate_proxy_mad":duplicate_threshold,"continuity_seconds":continuity_seconds,"feature_floor":feature_floor,"algorithm":"blur + local proxy difference + ORB support + endpoint/continuity protection; no AI"}
    report={"schema_version":SCHEMA_VERSION,"arm":"R2","control":"R1 remains unchanged","source_manifest_sha256":_sha(manifest_path),"candidate_count":len(frames),"selected_count":len(selected),"rejected_count":len(frames)-len(selected),"configuration":config,"frames":selected,"diagnostics":diagnostics,"warnings":["Thresholds are calibration hypotheses, not quality guarantees.","Diagnostics are proxy measurements; rejection is reversible by rerunning with thresholds or using R1.","Coverage and metric accuracy require reconstruction/reference evaluation."],"deterministic":True}
    (out/'selection_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8'); (out/'diagnostics.jsonl').write_text('\n'.join(json.dumps(x,sort_keys=True) for x in diagnostics)+'\n',encoding='utf-8'); (out/'selection_timing.json').write_text(json.dumps({"elapsed_seconds":time.monotonic()-started},indent=2),encoding='utf-8'); return report

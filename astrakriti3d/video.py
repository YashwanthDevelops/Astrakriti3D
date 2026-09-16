"""Deterministic, timestamp-preserving video preparation."""
import hashlib, json, shutil, subprocess, time
from pathlib import Path

SUPPORTED={".mp4",".mov",".mkv",".avi",".webm",".mts",".m4v"}
class VideoPreparationError(RuntimeError): pass

COMMAND_TIMEOUT_SECONDS = 300

def _run(cmd, timeout=COMMAND_TIMEOUT_SECONDS):
    try: return subprocess.run(cmd,capture_output=True,text=True,check=False,timeout=timeout)
    except subprocess.TimeoutExpired as e: raise VideoPreparationError(f"command timed out after {timeout}s: {' '.join(cmd[:2])}") from e
    except FileNotFoundError as e: raise VideoPreparationError(f"required executable unavailable: {cmd[0]}") from e

def inspect_video(video, ffprobe="ffprobe"):
    p=Path(video)
    if not p.is_file(): raise VideoPreparationError(f"video does not exist: {p}")
    if p.suffix.lower() not in SUPPORTED: raise VideoPreparationError(f"unsupported video format: {p.suffix or '<none>'}")
    if not shutil.which(ffprobe): raise VideoPreparationError("ffprobe is unavailable; install FFmpeg and ensure ffprobe is on PATH")
    cmd=[ffprobe,"-v","error","-print_format","json","-show_streams","-show_format",str(p)]
    r=_run(cmd)
    if r.returncode: raise VideoPreparationError(f"ffprobe failed: {r.stderr[-1000:]}")
    try: raw=json.loads(r.stdout)
    except json.JSONDecodeError as e: raise VideoPreparationError("ffprobe returned malformed JSON") from e
    streams=raw.get("streams",[]); vs=next((s for s in streams if s.get("codec_type")=="video"),None)
    if not vs: raise VideoPreparationError("input has no video stream")
    duration=float(raw.get("format",{}).get("duration") or vs.get("duration") or 0)
    if duration<=0: raise VideoPreparationError("video duration is unavailable or non-positive")
    tags=vs.get("tags",{}); side=vs.get("side_data_list",[])
    rotation=tags.get("rotate")
    for s in side:
        if "rotation" in s: rotation=s["rotation"]
    return {"video_path":str(p.resolve()),"duration_seconds":duration,"width":vs.get("width"),"height":vs.get("height"),"codec":vs.get("codec_name"),"codec_long_name":vs.get("codec_long_name"),"frame_rate":vs.get("r_frame_rate"),"avg_frame_rate":vs.get("avg_frame_rate"),"time_base":vs.get("time_base"),"start_time":vs.get("start_time"),"rotation":rotation,"stream_index":vs.get("index"),"streams":streams,"raw_ffprobe":raw}

def iter_frame_timestamps(video, ffprobe="ffprobe", timeout=COMMAND_TIMEOUT_SECONDS):
    """Yield compact frame records without accumulating the source frame list."""
    cmd=[ffprobe,"-v","error","-select_streams","v:0",
         "-show_entries","packet=pts_time",
         "-of","compact=p=0:nk=1",str(video)]
    try:
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              text=True,encoding="utf-8",errors="replace",bufsize=1)
    except FileNotFoundError as e: raise VideoPreparationError(f"required executable unavailable: {cmd[0]}") from e
    started=time.monotonic(); count=0
    try:
        for raw in proc.stdout:
            if time.monotonic()-started > timeout:
                proc.kill(); raise VideoPreparationError(f"frame timestamp scan timed out after {timeout}s")
            line=raw.strip()
            if not line: continue
            fields=line.split("|")
            if not fields or fields[0] in ("N/A",""):
                raise VideoPreparationError(f"missing timestamp record at source frame {count}")
            try: ts=float(fields[0]);
            except ValueError as e: raise VideoPreparationError(f"malformed timestamp record: {line[:200]}") from e
            if ts != ts or ts in (float("inf"),float("-inf")):
                raise VideoPreparationError(f"invalid timestamp record: {line[:200]}")
            width=int(fields[1]) if len(fields)>1 and fields[1] not in ("N/A","") else None
            height=int(fields[2]) if len(fields)>2 and fields[2] not in ("N/A","") else None
            yield {"source_frame_index":count,"source_timestamp_seconds":ts,"width":width,"height":height}
            count += 1
        stderr=proc.stderr.read() if proc.stderr else ""
        code=proc.wait(timeout=max(1,timeout-int(time.monotonic()-started)))
    except subprocess.TimeoutExpired as e:
        proc.kill(); raise VideoPreparationError(f"frame timestamp scan timed out after {timeout}s") from e
    finally:
        if proc.poll() is None: proc.kill()
    if code: raise VideoPreparationError(f"frame timestamp scan failed: {stderr[-1000:]}")
    if count==0: raise VideoPreparationError("no usable presentation timestamps were reported")

def frame_timestamps(video, ffprobe="ffprobe"):
    """Compatibility helper; callers needing bounded memory should iterate instead."""
    return list(iter_frame_timestamps(video,ffprobe))

def _jpeg_dimensions(path):
    data=Path(path).read_bytes()
    if data[:2] != b"\xff\xd8": raise VideoPreparationError(f"extracted file is not a JPEG: {path}")
    i=2
    while i+9 < len(data):
        if data[i] != 0xff: i += 1; continue
        marker=data[i+1]; i += 2
        if marker in (0xd8,0xd9): continue
        if i+2 > len(data): break
        length=int.from_bytes(data[i:i+2],"big")
        if marker in range(0xc0,0xc4) or marker in range(0xc5,0xc8) or marker in range(0xc9,0xcc) or marker in range(0xcd,0xd0):
            if i+7 > len(data): break
            return {"width":int.from_bytes(data[i+5:i+7],"big"),"height":int.from_bytes(data[i+3:i+5],"big")}
        i += length
    raise VideoPreparationError(f"JPEG dimensions unavailable: {path}")

def _target_timestamps(video, interval_seconds, ffprobe):
    targets=[]; next_target=0.0; last_ts=None
    for f in iter_frame_timestamps(video,ffprobe):
        ts=f["source_timestamp_seconds"]
        if last_ts is not None and ts < last_ts: raise VideoPreparationError("source timestamps are not monotonic")
        last_ts=ts
        while ts >= next_target:
            if not targets or ts != targets[-1]["source_timestamp_seconds"]:
                targets.append(f)
            next_target += interval_seconds
    return targets

def _extract_sequential(src, frame_dir, interval_seconds, ffmpeg, expected_count):
    """Decode once and sample with FFmpeg's fps filter; no per-frame seeks."""
    pattern=str(frame_dir/"frame_%06d.jpg")
    fps=f"1/{interval_seconds:.12g}"
    cmd=[ffmpeg,"-hide_banner","-loglevel","error","-hwaccel","auto","-i",str(src),
         "-vf",f"fps={fps}","-q:v","2","-start_number","1","-frames:v",str(expected_count),"-y",pattern]
    r=_run(cmd,timeout=max(COMMAND_TIMEOUT_SECONDS, expected_count*2))
    files=sorted(frame_dir.glob("frame_*.jpg"))
    # EOF can legitimately leave the final interval boundary without a decoded
    # output frame. Accept that one-frame boundary shortfall, but never accept
    # a larger mismatch or extra files.
    if len(files) < max(1, expected_count-1) or len(files) > expected_count:
        raise VideoPreparationError(f"sequential extraction failed: expected {expected_count} JPEGs, got {len(files)}: {r.stderr[-500:]}")
    return files

def prepare_video(video, output, interval_seconds=1.0, ffmpeg="ffmpeg", ffprobe="ffprobe", extraction_mode="seek"):
    started=time.monotonic(); out=Path(output); out.mkdir(parents=True,exist_ok=True); src=Path(video)
    if not shutil.which(ffmpeg): raise VideoPreparationError("ffmpeg is unavailable; install FFmpeg and ensure ffmpeg is on PATH")
    report=inspect_video(src,ffprobe); duration=report["duration_seconds"]
    frame_dir=out/"frames"; frame_dir.mkdir(exist_ok=True)
    for old_frame in frame_dir.glob("frame_*.jpg"):
        try: old_frame.unlink()
        except OSError: pass
    if extraction_mode not in {"seek","sequential"}: raise VideoPreparationError("extraction_mode must be 'seek' or 'sequential'")
    targets=_target_timestamps(src,interval_seconds,ffprobe)
    manifest=[]
    if extraction_mode == "sequential":
        files=_extract_sequential(src,frame_dir,interval_seconds,ffmpeg,len(targets))
        extracted=list(zip(targets,files))
    else:
        extracted=[]
    next_target=0.0
    for f in targets if extraction_mode == "seek" else []:
        ts=f["source_timestamp_seconds"]
        while ts >= next_target:
            dest=frame_dir/f"frame_{len(extracted)+1:06d}.jpg"
            if manifest and ts == manifest[-1]["source_timestamp_seconds"]:
                next_target += interval_seconds; continue
            _extract_frame(src,dest,ts,ffmpeg)
            extracted.append((f,dest)); next_target += interval_seconds; break
    for f,dest in extracted:
        n=len(manifest)+1; name=f"frame_{n:06d}.jpg"; dest=Path(dest)
        if dest.name != name: dest.rename(frame_dir/name); dest=frame_dir/name
        actual_dims=_jpeg_dimensions(dest)
        manifest.append({"output_filename":name,"output_path":str(dest.resolve()),"source_frame_index":f["source_frame_index"],"source_timestamp_seconds":f["source_timestamp_seconds"],"dimensions":actual_dims,"source_dimensions":{"width":f.get("width") or report["width"],"height":f.get("height") or report["height"]},"transformations":{"rotation":report.get("rotation"),"extraction":f"ffmpeg {extraction_mode} extraction; FFmpeg default autorotation applied"},"sha256":hashlib.sha256(dest.read_bytes()).hexdigest()})
    selected_count=len(manifest)
    if not manifest: raise VideoPreparationError("sampling produced no frames")
    if manifest[-1]["source_timestamp_seconds"] > duration: raise VideoPreparationError("selected timestamp exceeds video duration")
    if any(b["source_timestamp_seconds"]<a["source_timestamp_seconds"] for a,b in zip(manifest,manifest[1:])): raise VideoPreparationError("selected timestamps are not monotonic")
    result={"schema_version":"1.1","sampling":{"rule":"first decoded frame at or after each interval boundary","interval_seconds":interval_seconds,"extraction_mode":extraction_mode},"video":report,"frames":manifest,"output_count":len(manifest),"elapsed_seconds":time.monotonic()-started,"assumptions":["timestamps are streamed source presentation timestamps reported by ffprobe","FFmpeg default autorotation is applied during extraction and recorded"],"unknowns":[]}
    (out/"ffprobe.json").write_text(json.dumps(report.get("raw_ffprobe",{}),indent=2)); clean=dict(report); clean.pop("raw_ffprobe",None); (out/"inspection.json").write_text(json.dumps(clean,indent=2)); (out/"manifest.json").write_text(json.dumps(result,indent=2)); (out/"preparation_report.json").write_text(json.dumps(result,indent=2)); return result

def _extract_frame(src,dest,ts,ffmpeg):
    cmd=[ffmpeg,"-hide_banner","-loglevel","error","-hwaccel","auto","-ss",f"{ts:.6f}","-i",str(src),"-frames:v","1","-q:v","2","-y",str(dest)]
    r=_run(cmd)
    if r.returncode or not dest.is_file() or dest.stat().st_size==0:
        cmd_sw=[ffmpeg,"-hide_banner","-loglevel","error","-ss",f"{ts:.6f}","-i",str(src),"-frames:v","1","-q:v","2","-y",str(dest)]
        r=_run(cmd_sw)
    if r.returncode or not dest.is_file() or dest.stat().st_size==0:
        if dest.exists(): dest.unlink()
        raise VideoPreparationError(f"frame extraction failed at {ts:.6f}s: {r.stderr[-500:]}")

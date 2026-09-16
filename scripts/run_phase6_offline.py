"""Offline Phase 6 comparison. This command never imports or calls WebODM."""
from __future__ import annotations
import argparse, hashlib, json, shutil, time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astrakriti3d.resources import require_memory, snapshot
from astrakriti3d.selection_preflight import validate_selection

def main():
    p=argparse.ArgumentParser(description="Compare existing Phase 6 frame lists without WebODM")
    p.add_argument("--r1-images",required=True); p.add_argument("--r2-images",required=True); p.add_argument("--r2-exact-images",required=True)
    p.add_argument("--geo-txt",required=True); p.add_argument("--output",required=True); p.add_argument("--threads",type=int,default=1); p.add_argument("--min-memory-bytes",type=int,default=0)
    a=p.parse_args(); out=Path(a.output); out.mkdir(parents=True,exist_ok=False)
    if a.min_memory_bytes: before=require_memory(a.min_memory_bytes,a.threads)
    else: before=snapshot(a.threads)
    arms={}; base_names={p.name for p in Path(a.r1_images).iterdir() if p.is_file()}
    for name, directory in (("R1-194",a.r1_images),("R2-192",a.r2_images),("R2-185",a.r2_exact_images)):
        started=time.perf_counter(); names={p.name for p in Path(directory).iterdir() if p.is_file()}
        source_lines=Path(a.geo_txt).read_text(encoding='utf-8').splitlines()
        if not source_lines or source_lines[0] != 'EPSG:4326': raise ValueError('geo.txt must begin with EPSG:4326')
        arm_geo=out/(name.replace('-','_')+'.geo.txt'); arm_geo.write_text('\n'.join([source_lines[0]]+[line for line in source_lines[1:] if line.split() and line.split()[0] in names])+'\n',encoding='utf-8')
        check=validate_selection(directory,arm_geo)
        removed=sorted(base_names-names); added=sorted(names-base_names)
        arms[name]={"frame_count":len(names),"removed_from_R1":removed,"added_vs_R1":added,"geo_txt":str(arm_geo.resolve()),"preflight":check,"selector_runtime_seconds":time.perf_counter()-started,"resources":snapshot(a.threads)}
    report={"schema_version":"phase6.offline-experiment.v1","offline_only":True,"webodm_submitted":False,"source_lists":{"R1":str(Path(a.r1_images).resolve()),"R2_192":str(Path(a.r2_images).resolve()),"R2_185":str(Path(a.r2_exact_images).resolve())},"arms":arms,"resources_before":before,"configuration":{"threads":a.threads,"min_memory_bytes":a.min_memory_bytes},"warnings":["Offline checks do not establish reconstruction quality, coverage, accuracy or WebODM runtime.","185-frame approach remains unpromoted."]}
    (out/'experiment_metadata.json').write_text(json.dumps(report,indent=2),encoding='utf-8'); print(json.dumps(report,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())

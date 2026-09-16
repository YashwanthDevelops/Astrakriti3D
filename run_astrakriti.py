import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from astrakriti3d.video import VideoPreparationError,prepare_video
from astrakriti3d.telemetry import TelemetryError,MissingInputError,UnsupportedSchemaError,MalformedTelemetryError,inspect_metadata
from astrakriti3d.geolocation import GeolocationError,prepare_geolocation
from astrakriti3d.project import ProjectPreparationError,prepare_project
from astrakriti3d.preflight import run_preflight
from astrakriti3d.recovery import run_reconstruction
from astrakriti3d.orchestrator import run_pipeline, RunOrchestrationError
from astrakriti3d.baseline import BaselineError,inventory_baseline
from astrakriti3d.selection import SelectionError,select_frames,adaptive_select_frames
from astrakriti3d.selection_preflight import validate_selection,classify_failure
def main():
 p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True); q=sub.add_parser("prepare"); q.add_argument("--video",required=True); q.add_argument("--output",required=True); q.add_argument("--mode",choices=("local","georeferenced"),default=None); q.add_argument("--srt"); q.add_argument("--tolerance",type=float,default=.5); q.add_argument("--time-offset",type=float,default=0.0); q.add_argument("--interval-seconds",type=float,default=1.0); q.add_argument("--extraction-mode",choices=("seek","sequential"),default="seek")
 m=sub.add_parser("inspect-metadata"); m.add_argument("--video",required=True); m.add_argument("--srt",required=True); m.add_argument("--manifest",required=True); m.add_argument("--output",required=True); m.add_argument("--tolerance",type=float,default=.5); m.add_argument("--time-offset",type=float,default=0.0)
 g=sub.add_parser("prepare-geolocation"); g.add_argument("--video",required=True); g.add_argument("--manifest",required=True); g.add_argument("--associations",required=True); g.add_argument("--output",required=True); g.add_argument("--tolerance",type=float,default=.5)
 pf=sub.add_parser("preflight"); pf.add_argument("--mode",choices=("local","georeferenced"),required=True); pf.add_argument("--video",required=True); pf.add_argument("--srt"); pf.add_argument("--output",required=True)
 rc=sub.add_parser("reconstruct"); rc.add_argument("--mode",choices=("local","georeferenced"),required=True); rc.add_argument("--video",required=True); rc.add_argument("--images",required=True); rc.add_argument("--output",required=True); rc.add_argument("--srt"); rc.add_argument("--geo-txt"); rc.add_argument("--selector-config"); rc.add_argument("--cancel-after",type=float); rc.add_argument("--poll-seconds",type=float,default=3.0)
 rn=sub.add_parser("run"); rn.add_argument("--mode",choices=("local","georeferenced"),required=True); rn.add_argument("--video",required=True); rn.add_argument("--srt"); rn.add_argument("--output",required=True); rn.add_argument("--cancel-after",type=float); rn.add_argument("--poll-seconds",type=float,default=3.0)
 b=sub.add_parser("baseline-inventory"); b.add_argument("--result",required=True); b.add_argument("--output",required=True); b.add_argument("--phase4-dir")
 s=sub.add_parser("select-frames"); s.add_argument("--manifest",required=True); s.add_argument("--frames",required=True); s.add_argument("--output",required=True); s.add_argument("--min-blur",type=float,default=10.0); s.add_argument("--duplicate-threshold",type=float,default=1.5); s.add_argument("--continuity-seconds",type=float,default=2.0); s.add_argument("--feature-floor",type=int,default=20)
 ad=sub.add_parser("adaptive-select"); ad.add_argument("--manifest",required=True); ad.add_argument("--frames",required=True); ad.add_argument("--output",required=True); ad.add_argument("--target-fps",type=float,default=2.0); ad.add_argument("--min-feature-displacement",type=float,default=12.0); ad.add_argument("--min-new-feature-ratio",type=float,default=.20); ad.add_argument("--min-useful-matches",type=int,default=80); ad.add_argument("--min-features",type=int,default=150); ad.add_argument("--max-gap-seconds",type=float,default=2.0); ad.add_argument("--min-blur",type=float,default=10.0); ad.add_argument("--max-clipped-ratio",type=float,default=.15); ad.add_argument("--dry-run",action="store_true"); ad.add_argument("--selection-report")
 d=sub.add_parser("diagnose-selection"); d.add_argument("--images",required=True); d.add_argument("--geo-txt",required=True); d.add_argument("--selection-manifest"); d.add_argument("--log"); d.add_argument("--output",required=True)
 a=p.parse_args()
 if a.command == "prepare":
  try: r=prepare_project(a.video,a.output,mode=a.mode,srt=a.srt,interval_seconds=a.interval_seconds,extraction_mode=a.extraction_mode,tolerance=a.tolerance,time_offset=a.time_offset); print(json.dumps({"ok":True,"report":r},indent=2)); return 0
  except (VideoPreparationError,ProjectPreparationError,TelemetryError,GeolocationError) as e: print(json.dumps({"ok":False,"error":{"type":"project_preparation","message":str(e)}},indent=2)); return 3
 if a.command == "inspect-metadata":
  try:
   report=inspect_metadata(a.video,a.srt,a.manifest,a.output,a.tolerance,a.time_offset)
   code=0 if report["association"]["matched_count"]==report["association"]["frame_count"] else (5 if report["association"]["matched_count"] else 4)
   print(json.dumps({"ok":code==0,"report":report},indent=2)); return code
  except MissingInputError as e: print(json.dumps({"ok":False,"error":{"type":"missing_input","message":str(e)}},indent=2)); return 2
  except UnsupportedSchemaError as e: print(json.dumps({"ok":False,"error":{"type":"unsupported_schema","message":str(e)}},indent=2)); return 3
  except MalformedTelemetryError as e: print(json.dumps({"ok":False,"error":{"type":"malformed_telemetry","message":str(e)}},indent=2)); return 3
  except TelemetryError as e: print(json.dumps({"ok":False,"error":{"type":"telemetry","message":str(e)}},indent=2)); return 3
 if a.command == "preflight":
  try:
   report=run_preflight(a.video,a.output,mode=a.mode,srt=a.srt)
   print(json.dumps(report,indent=2)); return 0 if report["status"] == "PASS" else 3
  except (ValueError,FileNotFoundError,VideoPreparationError) as e:
   print(json.dumps({"ok":False,"error":{"type":"preflight","message":str(e)}},indent=2)); return 3
 if a.command == "reconstruct":
  try:
   result=run_reconstruction(a.video,a.images,a.output,mode=a.mode,srt=a.srt,geo_txt=a.geo_txt,selector_config=a.selector_config,cancel_after=a.cancel_after,poll_seconds=a.poll_seconds)
   print(json.dumps(result,indent=2)); return 0 if result.get("ok") else 3
  except (ValueError,FileNotFoundError) as e:
   print(json.dumps({"ok":False,"error":{"type":"reconstruction","message":str(e)}},indent=2)); return 3
 if a.command == "run":
  try:
   result=run_pipeline(a.video,a.output,mode=a.mode,srt=a.srt,cancel_after=a.cancel_after,poll_seconds=a.poll_seconds)
   print(json.dumps(result,indent=2)); return 0 if result.get("ok") else 3
  except (RunOrchestrationError,ValueError,FileNotFoundError) as e:
   print(json.dumps({"ok":False,"error":{"type":"run","message":str(e)}},indent=2)); return 3
 if a.command == "prepare-geolocation":
  try:
   report=prepare_geolocation(a.video,a.manifest,a.associations,a.output,a.tolerance); print(json.dumps({"ok":True,"report":report},indent=2)); return 0
  except (GeolocationError,FileNotFoundError,ValueError) as e: print(json.dumps({"ok":False,"error":{"type":"geolocation_preparation","message":str(e)}},indent=2)); return 3
 if a.command == "baseline-inventory":
  try: print(json.dumps({"ok":True,"report":inventory_baseline(a.result,a.output,a.phase4_dir)},indent=2)); return 0
  except (BaselineError,ValueError,FileNotFoundError) as e: print(json.dumps({"ok":False,"error":{"type":"baseline_inventory","message":str(e)}},indent=2)); return 3
 if a.command == "select-frames":
  try: print(json.dumps({"ok":True,"report":select_frames(a.manifest,a.frames,a.output,a.min_blur,a.duplicate_threshold,a.continuity_seconds,a.feature_floor)},indent=2)); return 0
  except (SelectionError,ValueError,FileNotFoundError) as e: print(json.dumps({"ok":False,"error":{"type":"selection","message":str(e)}},indent=2)); return 3
 if a.command == "adaptive-select":
  try:
   opts={k:getattr(a,k) for k in ("target_fps","min_feature_displacement","min_new_feature_ratio","min_useful_matches","min_features","max_gap_seconds","min_blur","max_clipped_ratio","dry_run","selection_report")}
   print(json.dumps({"ok":True,"report":adaptive_select_frames(a.manifest,a.frames,a.output,**opts)},indent=2)); return 0
  except (SelectionError,ValueError,FileNotFoundError) as e: print(json.dumps({"ok":False,"error":{"type":"adaptive_selection","message":str(e)}},indent=2)); return 3
 if a.command == "diagnose-selection":
  try:
   report={"preflight":validate_selection(a.images,a.geo_txt,a.selection_manifest)}
   if a.log: report["failure"]=classify_failure(a.log)
   Path(a.output).parent.mkdir(parents=True,exist_ok=True); Path(a.output).write_text(json.dumps(report,indent=2),encoding="utf-8")
   print(json.dumps({"ok":report["preflight"]["valid"],"report":report},indent=2)); return 0 if report["preflight"]["valid"] else 3
  except (ValueError,FileNotFoundError,KeyError) as e: print(json.dumps({"ok":False,"error":{"type":"selection_diagnosis","message":str(e)}},indent=2)); return 3
if __name__=="__main__": sys.exit(main())

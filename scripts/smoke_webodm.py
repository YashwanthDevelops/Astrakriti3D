import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from astrakriti3d.config import Config
from astrakriti3d.runner import run
def main():
 p=argparse.ArgumentParser(); p.add_argument("--images"); p.add_argument("--geo-txt"); p.add_argument("--output",default="runs/smoke"); p.add_argument("--options"); p.add_argument("--cancel-after",type=float); a=p.parse_args(); options=json.loads(Path(a.options).read_text()) if a.options else []
 if not a.images: print(json.dumps({"schema_version":"1.0","ok":False,"error":{"type":"validation","message":"--images is required"}},indent=2)); return 4
 geo_txt=a.geo_txt
 if not geo_txt:
  ip=Path(a.images)
  if (ip/"geo.txt").is_file(): geo_txt=str(ip/"geo.txt")
  elif (ip.parent/"geo.txt").is_file(): geo_txt=str(ip.parent/"geo.txt")
 r=run(Config.from_env(),a.images,a.output,options,a.cancel_after,geo_txt=geo_txt)
 out_dir=Path(a.output); out_dir.mkdir(parents=True,exist_ok=True); (out_dir/"result.json").write_text(json.dumps(r,indent=2),encoding="utf-8")
 print(json.dumps(r,indent=2)); return 0 if r.get("ok") else (5 if r.get("cancelled") else 3 if r.get("error",{}).get("type")=="ValueError" else 2)
if __name__=="__main__": sys.exit(main())

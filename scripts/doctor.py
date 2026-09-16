import argparse,json,os,platform,shutil,subprocess,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from astrakriti3d.config import Config
def check(ok,value=None,error=None): return {"status":"passed" if ok else "failed","value":value,"error":None if ok else error}
def main():
 c=Config.from_env(); out={"schema_version":"1.0","checks":{},"webodm":{"url":c.base_url,"credentials_configured":bool(c.username and c.password)}}
 out["checks"]["os_python"]={"status":"passed","os":platform.platform(),"python":platform.python_version(),"interpreter":sys.executable}
 try:
  import psutil; out["checks"]["resources"]={"status":"passed","cpu":psutil.cpu_count(),"ram_bytes":psutil.virtual_memory().total,"disk_free_bytes":shutil.disk_usage('.').free}
 except Exception as e: out["checks"]["resources"]=check(False,error=str(e))
 for exe in ("ffmpeg","ffprobe","docker"):
  try: out["checks"][exe]=check(True,subprocess.run([exe,"--version" if exe=="docker" else "-version"],capture_output=True,text=True,timeout=5).stdout.splitlines()[0])
  except Exception as e: out["checks"][exe]=check(False,error=str(e))
 out["checks"]["image_fixture"]=check(any(Path("inputs").glob("*.jpg")) or any(Path("inputs").glob("*.png")),error="no project-local image fixture")
 if c.base_url:
  try: urllib.request.urlopen(c.base_url,timeout=c.timeout); out["checks"]["webodm_reachable"]=check(True)
  except Exception as e: out["checks"]["webodm_reachable"]=check(False,error=str(e))
 else: out["checks"]["webodm_reachable"]={"status":"unknown","error":"WEBODM_BASE_URL is not configured"}
 out["checks"]["credentials"]=check(bool(c.username and c.password),error="WEBODM_USERNAME/WEBODM_PASSWORD missing")
 text=json.dumps(out,indent=2); print(text); a=argparse.ArgumentParser(); a.add_argument("--output"); args=a.parse_args()
 if args.output: Path(args.output).parent.mkdir(parents=True,exist_ok=True); Path(args.output).write_text(text+"\n")
if __name__=="__main__": main()

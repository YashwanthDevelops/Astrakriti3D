import hashlib, json, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
import psutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astrakriti3d.client import WebODMClient
from astrakriti3d.config import Config
from astrakriti3d.storage import fingerprint, manifest_for_images

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/phase18/coverage-aware-20260915-v14/webodm"
INPUT = ROOT / "evidence/phase18/coverage-aware-20260915-v14"
PROJECT = "2"
R1 = "ef1199ec-d6d3-4a3f-91c3-70f38f41de1c"
OPTIONS = []

def utc(): return datetime.now(timezone.utc).isoformat()
def write(path, value): path.write_text(json.dumps(value, indent=2), encoding="utf-8")
def append(path, value):
    with path.open("a", encoding="utf-8") as f: f.write(json.dumps(value, separators=(",", ":")) + "\n")
def resources():
    vm = psutil.virtual_memory(); disk = psutil.disk_usage(str(ROOT.drive or "C:"))
    gpu = None
    try:
        p = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        gpu = {"exit_code": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except Exception as e: gpu = {"available": False, "error": str(e)}
    return {"timestamp": utc(), "ram_available_bytes": vm.available, "ram_used_bytes": vm.used, "disk_free_bytes": disk.free, "gpu": gpu}
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "submission.json").exists(): raise SystemExit("refusing duplicate WebODM submission")
    validation = json.loads((INPUT / "validation_report.json").read_text(encoding="utf-8"))
    if not validation["valid"]: raise SystemExit("coverage-aware input validation failed")
    manifest = manifest_for_images(INPUT / "frames")
    geo = INPUT / "geo.txt"
    fp = fingerprint(manifest, OPTIONS, hashlib.sha256(geo.read_bytes()).hexdigest())
    client = WebODMClient(Config.from_env()); client.authenticate()
    baseline = client.task(PROJECT, R1)
    node = next((x for x in client.request("GET", "/processingnodes/").json() if x.get("id") == 1), None)
    if baseline.get("status") != 40: raise SystemExit("R1 baseline is not successful")
    if baseline.get("options") != OPTIONS: raise SystemExit("R1 options differ")
    if not node or not node.get("online") or int(node.get("queue_count", 0)) != 0: raise SystemExit("WebODM node is not idle")
    write(OUT / "baseline_snapshot.json", {"task_id": R1, "status": baseline.get("status"), "processing_time": baseline.get("processing_time"), "options": baseline.get("options"), "node": node, "captured_at": utc()})
    append(OUT / "resource_log.jsonl", resources())
    submitted = utc(); task_id = client.submit_task(PROJECT, manifest, OPTIONS, geo_txt=geo)
    write(OUT / "submission.json", {"task_id": task_id, "project_id": PROJECT, "submitted_at": submitted, "frame_count": len(manifest), "options": OPTIONS, "fingerprint": fp, "geo_sha256": hashlib.sha256(geo.read_bytes()).hexdigest(), "baseline_task_id": R1})
    terminal = None; started = time.monotonic()
    while time.monotonic() - started < 8 * 60 * 60:
        task = client.task(PROJECT, task_id)
        append(OUT / "status_events.jsonl", {"timestamp": utc(), "status": task.get("status"), "upload_progress": task.get("upload_progress"), "running_progress": task.get("running_progress"), "processing_time": task.get("processing_time"), "last_error": task.get("last_error")})
        append(OUT / "resource_log.jsonl", resources())
        (OUT / "webodm-output-live.log").write_text(client.output(PROJECT, task_id), encoding="utf-8")
        if task.get("status") in (30, 40, 50): terminal = task; break
        time.sleep(15)
    if terminal is None: raise SystemExit("monitor deadline reached; task left running")
    (OUT / "webodm-output-final.log").write_text(client.output(PROJECT, task_id), encoding="utf-8")
    inventory = []
    if terminal.get("status") == 40:
        dest = OUT / "artifacts"; dest.mkdir(exist_ok=True)
        for name in ("orthophoto.tif", "shots.geojson", "cameras.json", "report.pdf", "georeferenced_model.laz", "textured_model.zip", "textured_model.glb"):
            if name in (terminal.get("available_assets") or []):
                path = dest / name; client.download(PROJECT, task_id, name, path)
                inventory.append({"name": name, "path": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write(OUT / "task_final.json", {"task": terminal, "task_id": task_id, "terminal_status": terminal.get("status"), "processing_time": terminal.get("processing_time"), "completed_at": utc(), "artifact_inventory": inventory})
    print(json.dumps({"task_id": task_id, "terminal_status": terminal.get("status"), "processing_time": terminal.get("processing_time"), "artifact_count": len(inventory), "fingerprint": fp}, indent=2))
if __name__ == "__main__": main()

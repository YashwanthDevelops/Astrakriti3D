import hashlib, json, os, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astrakriti3d.client import WebODMClient
from astrakriti3d.config import Config
from astrakriti3d.storage import fingerprint, manifest_for_images

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/phase16/aggressive-webodm-20260915"
IMAGES = OUT / "input/images"
GEO = OUT / "input/geo.txt"
STATUS_LOG = OUT / "status_events.jsonl"
RESOURCE_LOG = OUT / "resource_log.jsonl"
POLL_SECONDS = 15
OUTPUT_SECONDS = 60
DEADLINE_SECONDS = 8 * 60 * 60


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def append_jsonl(path, value):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, separators=(",", ":")) + "\n")


def resources():
    disk = psutil.disk_usage(str(ROOT.drive or "C:\\"))
    gpu = None
    try:
        p = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        gpu = {"exit_code": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except Exception as exc:
        gpu = {"available": False, "error": str(exc)}
    vm = psutil.virtual_memory()
    return {
        "timestamp": utc(),
        "ram_total_bytes": vm.total,
        "ram_available_bytes": vm.available,
        "ram_used_bytes": vm.used,
        "disk_free_bytes": disk.free,
        "disk_total_bytes": disk.total,
        "gpu": gpu,
        "nodeodx_processes": [{"pid": p.pid, "name": p.name(), "rss": p.memory_info().rss} for p in psutil.process_iter(["name"]) if (p.info.get("name") or "").lower() in {"nodeodx.exe", "nodeodx"}],
    }


def download_artifacts(client, project_id, task_id, task):
    destination = OUT / "artifacts"
    destination.mkdir(parents=True, exist_ok=True)
    names = ("orthophoto.tif", "shots.geojson", "cameras.json", "report.pdf", "georeferenced_model.laz", "textured_model.zip", "textured_model.glb")
    inventory = []
    for name in names:
        if name not in (task.get("available_assets") or []):
            continue
        path = destination / name
        client.download(project_id, task_id, name, path)
        inventory.append({"name": name, "path": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_json(OUT / "artifact_inventory.json", {"task_id": task_id, "artifacts": inventory})
    return inventory


def main():
    preflight = json.loads((OUT / "preflight.json").read_text(encoding="utf-8"))
    if not preflight.get("valid"):
        raise SystemExit("input preflight is invalid; task not submitted")
    manifest = manifest_for_images(IMAGES)
    options = []
    geo_sha = hashlib.sha256(GEO.read_bytes()).hexdigest()
    fp = fingerprint(manifest, options, geo_sha)
    client = WebODMClient(Config.from_env())
    client.authenticate()
    existing_submission = OUT / "submission.json"
    if existing_submission.exists():
        submission = json.loads(existing_submission.read_text(encoding="utf-8"))
        task_id = submission["task_id"]
        if submission.get("fingerprint") != fp:
            raise SystemExit("existing submission fingerprint does not match current input; refusing to submit")
    else:
        project = client.request("GET", "/projects/2/").json()
        node = next((x for x in client.request("GET", "/processingnodes/").json() if x.get("id") == 1), None)
        baseline = client.task("2", "ef1199ec-d6d3-4a3f-91c3-70f38f41de1c")
        if baseline.get("status") != 40:
            raise SystemExit(f"R1 baseline is not successful (status={baseline.get('status')}); task not submitted")
        if baseline.get("options") != options:
            raise SystemExit("R1 options are not the default option list; task not submitted")
        if not node or not node.get("online") or int(node.get("queue_count", 0)) != 0:
            raise SystemExit("processing node is not online and idle; task not submitted")
        write_json(OUT / "baseline_snapshot.json", {"task_id": baseline["id"], "status": baseline.get("status"), "processing_time": baseline.get("processing_time"), "options": baseline.get("options"), "available_assets": baseline.get("available_assets"), "project": project, "node": node, "captured_at": utc()})
        append_jsonl(RESOURCE_LOG, resources())
        submitted_at = utc()
        task_id = client.submit_task("2", manifest, options, geo_txt=GEO)
        write_json(OUT / "submission.json", {"task_id": task_id, "project_id": "2", "submitted_at": submitted_at, "frame_count": len(manifest), "options": options, "fingerprint": fp, "geo_sha256": geo_sha, "baseline_task_id": baseline["id"], "baseline_options": baseline.get("options")})
    started = time.monotonic()
    last_output = 0
    terminal = None
    while time.monotonic() - started < DEADLINE_SECONDS:
        task = client.task("2", task_id)
        event = {"timestamp": utc(), "status": task.get("status"), "upload_progress": task.get("upload_progress"), "running_progress": task.get("running_progress"), "processing_time": task.get("processing_time"), "last_error": task.get("last_error")}
        append_jsonl(STATUS_LOG, event)
        append_jsonl(RESOURCE_LOG, resources())
        if time.monotonic() - last_output >= OUTPUT_SECONDS:
            (OUT / "webodm-output-live.log").write_text(client.output("2", task_id), encoding="utf-8")
            last_output = time.monotonic()
        raw_status = task.get("status")
        if raw_status is not None and int(raw_status) in (30, 40, 50):
            terminal = task
            break
        time.sleep(POLL_SECONDS)
    if terminal is None:
        raise SystemExit("monitor deadline reached; task left running and was not cancelled")
    (OUT / "webodm-output-final.log").write_text(client.output("2", task_id), encoding="utf-8")
    inventory = download_artifacts(client, "2", task_id, terminal) if int(terminal.get("status")) == 40 else []
    write_json(OUT / "task_final.json", {"task": terminal, "task_id": task_id, "terminal_status": terminal.get("status"), "processing_time": terminal.get("processing_time"), "completed_at": utc(), "artifact_inventory": inventory})
    print(json.dumps({"task_id": task_id, "terminal_status": terminal.get("status"), "processing_time": terminal.get("processing_time"), "artifact_count": len(inventory), "fingerprint": fp}, indent=2))


if __name__ == "__main__":
    main()

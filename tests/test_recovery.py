import json
from pathlib import Path
from astrakriti3d.recovery import run_reconstruction

class Response:
    status_code = 200
class BaseClient:
    def __init__(self, config): self.s=type("S",(),{"request":lambda self,*a,**k: Response()})()
    def authenticate(self): pass
    def find_or_create_project(self): return "p"
    def submit_task(self, p, m, o, geo_txt=None): return "task"
    def output(self, p, t): return "processing log"
    def download(self, p, t, asset, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True); Path(dest).write_text("artifact")
    def cancel(self, p, t): self.cancelled=True
    def task(self, p, t): return {"status": 40, "available_assets": ["shots.geojson"]}

def setup(tmp_path):
    video=tmp_path/"video.mp4"; video.write_bytes(b"video")
    images=tmp_path/"images"; images.mkdir(); (images/"a.jpg").write_bytes(b"a"); (images/"b.jpg").write_bytes(b"b")
    config=type("C",(),{"base_url":"http://webodm","username":"u","password":"p","timeout":1})()
    return video, images, config, lambda *a,**k:{"status":"PASS"}

def test_preflight_failure_prevents_submission(tmp_path):
    video, images, config, _=setup(tmp_path); submitted=[]
    class C(BaseClient):
        def submit_task(self,*a,**k): submitted.append(1)
    r=run_reconstruction(video,images,tmp_path/"runs",mode="local",config=config,preflight_runner=lambda *a,**k:{"status":"FAIL"},client_factory=C)
    assert not r["ok"] and not submitted and (Path(r["run_dir"])/"failure_report.json").is_file()

def test_successful_task_tracking(tmp_path):
    video, images, config, pre=setup(tmp_path)
    r=run_reconstruction(video,images,tmp_path/"runs",mode="local",config=config,preflight_runner=pre,client_factory=BaseClient,poll_seconds=0)
    assert r["ok"] and r["task_id"]=="task"
    d=Path(r["run_dir"]); assert (d/"run_manifest.json").is_file() and (d/"task_status.json").is_file() and (d/"processing_log.jsonl").is_file()

def test_transient_null_task_status_does_not_fail_submission(tmp_path):
    video, images, config, pre=setup(tmp_path)
    class C(BaseClient):
        calls = 0
        def task(self,p,t):
            self.calls += 1
            return {} if self.calls == 1 else {"status":40,"available_assets":["shots.geojson"]}
    r=run_reconstruction(video,images,tmp_path/"runs",mode="local",config=config,preflight_runner=pre,client_factory=C,poll_seconds=0)
    assert r["ok"]

def test_task_failure_capture_and_texrecon_classification(tmp_path):
    video, images, config, pre=setup(tmp_path)
    class C(BaseClient):
        def task(self,p,t): return {"status":30,"last_error":"texrecon failed mvs_texturing exit code 3221225477"}
    r=run_reconstruction(video,images,tmp_path/"runs",mode="local",config=config,preflight_runner=pre,client_factory=C,poll_seconds=0)
    report=json.loads((Path(r["run_dir"])/"failure_report.json").read_text()); assert report["category"]=="texrecon" and report["native_process"]=="texrecon" and report["exit_code"]=="3221225477"

def test_service_disconnection_is_preserved(tmp_path):
    video, images, config, pre=setup(tmp_path)
    class C(BaseClient):
        def task(self,p,t): raise ConnectionError("connection refused NodeODM")
    r=run_reconstruction(video,images,tmp_path/"runs",mode="local",config=config,preflight_runner=pre,client_factory=C,poll_seconds=0)
    assert not r["ok"] and json.loads((Path(r["run_dir"])/"failure_report.json").read_text())["category"]=="service_failure"

def test_cancellation_and_duplicate_run_safety(tmp_path):
    video, images, config, pre=setup(tmp_path)
    class C(BaseClient):
        def task(self,p,t): return {"status":20,"running_progress":1}
    a=run_reconstruction(video,images,tmp_path/"runs",mode="local",config=config,preflight_runner=pre,client_factory=C,poll_seconds=0,cancel_after=0)
    b=run_reconstruction(video,images,tmp_path/"runs",mode="local",config=config,preflight_runner=pre,client_factory=C,poll_seconds=0,cancel_after=0)
    assert not a["ok"] and not b["ok"] and a["run_dir"] != b["run_dir"]

def test_partial_outputs_are_not_marked_complete(tmp_path):
    video, images, config, pre=setup(tmp_path)
    class C(BaseClient):
        def task(self,p,t): return {"status":40,"available_assets":[]}
    r=run_reconstruction(video,images,tmp_path/"runs",mode="local",config=config,preflight_runner=pre,client_factory=C,poll_seconds=0)
    assert not r["ok"] and json.loads((Path(r["run_dir"])/"task_status.json").read_text())["status"]=="partial_output"

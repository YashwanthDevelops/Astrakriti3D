import json, hashlib
from pathlib import Path
import pytest
from astrakriti3d.baseline import BaselineError, inventory_baseline
from astrakriti3d.recovery import run_reconstruction


def test_recovery_reuses_persisted_task_after_restart(tmp_path):
    video = tmp_path / "video.mp4"; video.write_bytes(b"video")
    images = tmp_path / "images"; images.mkdir()
    for name in ("a.jpg", "b.jpg"):
        (images / name).write_bytes(name.encode())
    config = type("C", (), {"base_url": "http://webodm", "username": "u", "password": "p", "timeout": 1, "db_path": tmp_path / "jobs.sqlite"})()
    class Client:
        submits = 0
        def __init__(self, config): pass
        def authenticate(self): pass
        def find_or_create_project(self): return "p"
        def submit_task(self, *args, **kwargs): Client.submits += 1; return "remote-task"
        def task(self, p, t): return {"status": 40, "available_assets": ["shots.geojson"]}
        def output(self, p, t): return "output"
        def download(self, p, t, asset, destination):
            destination.parent.mkdir(parents=True, exist_ok=True); destination.write_text("asset")
        def cancel(self, p, t): pass
    pre = lambda *args, **kwargs: {"status": "PASS"}
    first = run_reconstruction(video, images, tmp_path / "runs", mode="local", config=config, preflight_runner=pre, client_factory=Client, poll_seconds=0)
    second = run_reconstruction(video, images, tmp_path / "runs", mode="local", config=config, preflight_runner=pre, client_factory=Client, poll_seconds=0)
    assert first["ok"] and second["ok"] and Client.submits == 1
    assert any(json.loads(line)["operation"] == "reconcile_task" for line in (tmp_path / "runs" / Path(second["run_dir"]).name / "api_log.jsonl").read_text().splitlines())

def fixture(tmp_path, complete=True):
    root=tmp_path/'run'; art=root/'artifacts'; art.mkdir(parents=True)
    files={'orthophoto.tif':b'II*\x00pixels','georeferenced_model.laz':b'LASFpoint','shots.geojson':json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'Point','coordinates':[1,2]}}]}).encode(),'cameras.json':b'{}','report.pdf':b'%PDF-1.7\n'}
    for n,d in files.items(): (art/n).write_bytes(d)
    items=[{'name':n,'path':str(art/n),'sha256':hashlib.sha256(d).hexdigest()} for n,d in files.items()]
    result={'ok':True,'local_job_id':'local','project_id':'p','task_id':'task','fingerprint':'fp','events':[{'timestamp':'2026-01-01T00:00:00+00:00','status':'running'},{'timestamp':'2026-01-01T00:00:02+00:00','status':'completed'}],'artifacts':items}
    if not complete: (art/'report.pdf').unlink()
    rp=root/'result.json'; rp.write_text(json.dumps(result)); return rp,root

def test_complete_inventory_and_hashes(tmp_path):
    rp,root=fixture(tmp_path); out=tmp_path/'out'; report=inventory_baseline(rp,out,root)
    assert report['reproducible'] and report['validation_summary']['all_hashes_match']
    assert report['timing']['inclusive_wall_seconds']==2.0
    assert (out/'baseline_inventory.json').exists()

def test_missing_artifact_is_detected(tmp_path):
    rp,root=fixture(tmp_path,False); report=inventory_baseline(rp,tmp_path/'out',root)
    assert not report['reproducible'] and report['missing_artifacts']

def test_bad_hash_and_malformed_json_are_invalid(tmp_path):
    rp,root=fixture(tmp_path); data=json.loads(rp.read_text()); data['artifacts'][0]['sha256']='bad'; rp.write_text(json.dumps(data)); (root/'artifacts'/'cameras.json').write_text('{bad')
    report=inventory_baseline(rp,tmp_path/'out',root)
    by={x['name']:x for x in report['artifacts']}
    assert not by['orthophoto.tif']['validation']['hash_match']
    assert by['cameras.json']['validation']['status']=='invalid'

def test_incomplete_result_rejected(tmp_path):
    p=tmp_path/'r.json'; p.write_text(json.dumps({'ok':False}))
    with pytest.raises(BaselineError): inventory_baseline(p,tmp_path/'out')

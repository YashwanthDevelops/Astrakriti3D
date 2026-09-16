import json
from pathlib import Path
import pytest
from astrakriti3d.preflight import run_preflight

def fake_video(monkeypatch):
    monkeypatch.setattr("astrakriti3d.preflight.inspect_video", lambda p: {"codec":"h264", "duration_seconds":2.0, "avg_frame_rate":"30/1", "width":4, "height":3})

def fake_baseline(root, spec): return {"valid": True, "issues": []}
def fake_resources(): return {"available_memory_bytes": 2 * 1024**3}
def fake_disk(path): return 20 * 1024**3

class Response:
    status_code = 200
class Client:
    def __init__(self, config):
        self.s = type("S", (), {"request": lambda self, *a, **k: Response()})()
    def authenticate(self): pass
    def request(self, method, path):
        return type("R", (), {"json": lambda self: [{"online": True, "queue_count": 0, "api_version": "2.3.1", "engine_version": "3.8.3", "available_options": []}]})()

def preflight(tmp_path, monkeypatch, mode="local", srt=None, **kwargs):
    fake_video(monkeypatch)
    video = tmp_path / "video.mp4"; video.write_bytes(b"video")
    defaults = {"client_factory": Client, "resource_probe": fake_resources, "disk_probe": fake_disk, "baseline_validator": fake_baseline}
    defaults.update(kwargs)
    return run_preflight(video, tmp_path / "out", mode=mode, srt=srt, config=type("C", (), {"base_url":"http://webodm", "username":"u", "password":"p", "timeout":1})(), **defaults)

def valid_srt(path):
    path.write_text("1\n00:00:00,000 --> 00:00:00,100\n[latitude: 1.0] [longitude: 2.0] [altitude: 4.0]\n", encoding="utf-8")

def test_local_video_only_passes_without_srt(tmp_path, monkeypatch):
    report = preflight(tmp_path, monkeypatch)
    assert report["status"] == "PASS" and report["mode"] == "local"
    assert report["checks"][-1]["name"] in {"webodm_versions", "queue_status"}

def test_georeferenced_video_plus_srt_passes(tmp_path, monkeypatch):
    srt = tmp_path / "video.srt"; valid_srt(srt)
    out = tmp_path / "out"; out.mkdir()
    (out / "manifest.json").write_text(json.dumps({"frames": [{"output_filename":"frame_000001.jpg", "source_timestamp_seconds":0.0}]}))
    report = preflight(tmp_path, monkeypatch, mode="georeferenced", srt=srt)
    assert report["status"] == "PASS"
    assert any(c["name"] == "geo_format" and c["status"] == "passed" for c in report["checks"])

def test_missing_srt_fails_georeferenced(tmp_path, monkeypatch):
    report = preflight(tmp_path, monkeypatch, mode="georeferenced")
    assert report["status"] == "FAIL" and any(c["name"] == "srt_exists" for c in report["checks"])

def test_malformed_srt_fails(tmp_path, monkeypatch):
    srt = tmp_path / "bad.srt"; srt.write_text("1\n00:00:00,000 --> 00:00:00,100\nnot telemetry\n")
    report = preflight(tmp_path, monkeypatch, mode="georeferenced", srt=srt)
    assert report["status"] == "FAIL"

def test_invalid_video_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("astrakriti3d.preflight.inspect_video", lambda p: (_ for _ in ()).throw(RuntimeError("bad video")))
    video = tmp_path / "video.mp4"; video.write_bytes(b"bad")
    report = run_preflight(video, tmp_path / "out", mode="local", config=type("C", (), {"base_url":"", "username":"", "password":"", "timeout":1})(), resource_probe=fake_resources, disk_probe=fake_disk, baseline_validator=fake_baseline)
    assert report["status"] == "FAIL"

def test_unavailable_webodm_fails(tmp_path, monkeypatch):
    report = preflight(tmp_path, monkeypatch)
    report = run_preflight(tmp_path / "video.mp4", tmp_path / "offline", mode="local", config=type("C", (), {"base_url":"", "username":"", "password":"", "timeout":1})(), resource_probe=fake_resources, disk_probe=fake_disk, baseline_validator=fake_baseline)
    assert report["status"] == "FAIL" and any(c["name"] == "webodm_api" for c in report["checks"])

def test_offline_nodeodm_fails(tmp_path, monkeypatch):
    class Offline(Client):
        def request(self, method, path): return type("R", (), {"json": lambda self: [{"online": False, "queue_count": 0}]})()
    report = preflight(tmp_path, monkeypatch, client_factory=Offline)
    assert report["status"] == "FAIL" and any(c["name"] == "nodeodm" and c["status"] == "failed" for c in report["checks"])

def test_insufficient_disk_fails(tmp_path, monkeypatch):
    report = preflight(tmp_path, monkeypatch, disk_probe=lambda p: 1)
    assert report["status"] == "FAIL" and any(c["name"] == "disk" for c in report["checks"])

def test_invalid_baseline_fails(tmp_path, monkeypatch):
    report = preflight(tmp_path, monkeypatch, baseline_validator=lambda root, spec: {"valid": False, "issues": ["changed"]})
    assert report["status"] == "FAIL" and any(c["name"] == "r1_baseline" for c in report["checks"])

def test_stale_telemetry_prevention(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"; video.write_bytes(b"video")
    out = tmp_path / "out"; out.mkdir(); (out / "geo.txt").write_text("EPSG:4326\n")
    fake_video(monkeypatch)
    report = run_preflight(video, out, mode="local", config=type("C", (), {"base_url":"", "username":"", "password":"", "timeout":1})(), resource_probe=fake_resources, disk_probe=fake_disk, baseline_validator=fake_baseline)
    assert report["status"] == "FAIL" and any(c["name"] == "stale_geolocation" for c in report["checks"])

def test_existing_writable_output_directory(tmp_path, monkeypatch):
    out = tmp_path / "out"; out.mkdir()
    fake_video(monkeypatch)
    video = tmp_path / "video.mp4"; video.write_bytes(b"video")
    report = run_preflight(video, out, mode="local", config=type("C", (), {"base_url":"", "username":"", "password":"", "timeout":1})(), resource_probe=fake_resources, disk_probe=fake_disk, baseline_validator=fake_baseline)
    check = next(c for c in report["checks"] if c["name"] == "output_writable")
    assert check["status"] == "passed" and check["requested_directory_exists"] is True

def test_missing_nested_output_directory_uses_writable_parent(tmp_path, monkeypatch):
    fake_video(monkeypatch)
    video = tmp_path / "video.mp4"; video.write_bytes(b"video")
    out = tmp_path / "nested" / "deeper" / "out"
    report = run_preflight(video, out, mode="local", config=type("C", (), {"base_url":"", "username":"", "password":"", "timeout":1})(), resource_probe=fake_resources, disk_probe=fake_disk, baseline_validator=fake_baseline)
    check = next(c for c in report["checks"] if c["name"] == "output_writable")
    assert check["status"] == "passed" and check["will_be_created"] is True

def test_read_only_parent_fails(tmp_path, monkeypatch):
    fake_video(monkeypatch)
    video = tmp_path / "video.mp4"; video.write_bytes(b"video")
    monkeypatch.setattr("astrakriti3d.preflight.os.access", lambda path, mode: False)
    report = run_preflight(video, tmp_path / "missing" / "out", mode="local", config=type("C", (), {"base_url":"", "username":"", "password":"", "timeout":1})(), resource_probe=fake_resources, disk_probe=fake_disk, baseline_validator=fake_baseline)
    assert next(c for c in report["checks"] if c["name"] == "output_writable")["status"] == "failed"

def test_output_path_occupied_by_file_fails(tmp_path, monkeypatch):
    fake_video(monkeypatch)
    video = tmp_path / "video.mp4"; video.write_bytes(b"video")
    out = tmp_path / "out"; out.write_bytes(b"not a directory")
    report = run_preflight(video, out, mode="local", config=type("C", (), {"base_url":"", "username":"", "password":"", "timeout":1})(), resource_probe=fake_resources, disk_probe=fake_disk, baseline_validator=fake_baseline)
    assert next(c for c in report["checks"] if c["name"] == "output_writable")["status"] == "failed"

def test_invalid_output_path_fails(tmp_path, monkeypatch):
    fake_video(monkeypatch)
    video = tmp_path / "video.mp4"; video.write_bytes(b"video")
    report = run_preflight(video, "bad\0path", mode="local", config=type("C", (), {"base_url":"", "username":"", "password":"", "timeout":1})(), resource_probe=fake_resources, disk_probe=fake_disk, baseline_validator=fake_baseline)
    assert report["status"] == "FAIL" and next(c for c in report["checks"] if c["name"] == "output_writable")["status"] == "failed"

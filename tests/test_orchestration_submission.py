import pytest
from astrakriti3d.config import Config
from astrakriti3d.runner import run
from astrakriti3d.storage import JobStore, fingerprint, manifest_for_images


class Fake:
    def __init__(self, fail=False): self.submits = 0; self.fail = fail
    def authenticate(self): pass
    def find_or_create_project(self): return "p"
    def submit_task(self, p, m, o, geo_txt=None):
        self.submits += 1
        if self.fail: raise ConnectionError("offline")
        return "t1"
    def task(self, p, t): return {"status": 50}
    def cancel(self, p, t): pass


def setup(tmp_path):
    images = tmp_path / "images"; images.mkdir()
    (images / "a.jpg").write_bytes(b"a"); (images / "b.jpg").write_bytes(b"b")
    return images, Config("http://fake", "u", "p", poll_interval=0, db_path=tmp_path / "jobs.sqlite3")


def test_submission_guard_calls_once_and_reuses_after_restart(tmp_path):
    images, cfg = setup(tmp_path); fake = Fake()
    first = run(cfg, images, tmp_path / "out", client=fake)
    second = run(cfg, images, tmp_path / "out2", client=fake)
    assert first["task_id"] == second["task_id"] == "t1" and fake.submits == 1


def test_existing_task_identity_is_reused_and_conflicts_rejected(tmp_path):
    images, cfg = setup(tmp_path); manifest = manifest_for_images(images); fp = fingerprint(manifest, [])
    store = JobStore(cfg.db_path); store.create("job", fp, manifest, [])
    store.update("job", project_id="p", task_id="existing", state="running")
    fake = Fake(); result = run(cfg, images, tmp_path / "out", client=fake)
    assert result["task_id"] == "existing" and fake.submits == 0
    with pytest.raises(ValueError): store.record_submission("job", "p", "other")


def test_failed_submission_can_retry(tmp_path):
    images, cfg = setup(tmp_path); fake = Fake(fail=True)
    first = run(cfg, images, tmp_path / "out", client=fake); assert not first["ok"]
    fake.fail = False; second = run(cfg, images, tmp_path / "out2", client=fake)
    assert fake.submits == 2 and second["task_id"] == "t1"

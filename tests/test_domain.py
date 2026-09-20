import pytest
from astrakriti3d.domain import ProductStore

def test_run_lifecycle_is_persistent_and_idempotent(tmp_path):
    path = tmp_path / "product.sqlite3"
    store = ProductStore(path)
    store.create_mission("m1", "Test mission", input_hashes={"video": "abc"})
    store.create_run("r1", "m1", "R1", "input-hash")
    for state in ("PREFLIGHT", "PREPARING", "READY", "SUBMITTED", "PROCESSING", "COMPLETED"):
        store.transition("r1", state)
    store.transition("r1", "COMPLETED")
    store.attach_webodm_task("r1", "task-1")
    reopened = ProductStore(path)
    run = reopened.get_run("r1")
    assert run.status == "COMPLETED" and run.webodm_task_id == "task-1"

def test_invalid_transition_is_rejected_and_failure_is_preserved(tmp_path):
    store = ProductStore(tmp_path / "product.sqlite3")
    store.create_mission("m1", "Test")
    store.create_run("r1", "m1", "R1", "hash")
    with pytest.raises(ValueError): store.transition("r1", "COMPLETED")
    store.transition("r1", "PREFLIGHT")
    store.transition("r1", "PREFLIGHT_FAILED")
    assert store.get_run("r1").status == "PREFLIGHT_FAILED"

@pytest.mark.parametrize("path", [
    ("PREFLIGHT", "PREPARING", "READY", "SUBMITTED", "PROCESSING", "COMPLETED"),
    ("PREFLIGHT", "PREFLIGHT_FAILED"),
    ("PREFLIGHT", "PREPARING", "PREPARATION_FAILED"),
    ("PREFLIGHT", "PREPARING", "READY", "CANCELLED"),
    ("PREFLIGHT", "PREPARING", "READY", "SUBMITTED", "PROCESSING", "PROCESSING_FAILED"),
    ("PREFLIGHT", "PREPARING", "READY", "SUBMITTED", "PROCESSING", "PARTIAL"),
    ("PREFLIGHT", "PREPARING", "READY", "SUBMITTED", "RECOVERY_REQUIRED", "PROCESSING"),
])
def test_supported_terminal_and_recovery_paths(tmp_path, path):
    store = ProductStore(tmp_path / ("-".join(path) + ".sqlite3"))
    store.create_mission("m1", "Test")
    store.create_run("r1", "m1", "R1", "hash")
    for state in path: store.transition("r1", state)
    assert store.get_run("r1").status == path[-1]

def test_artifacts_evidence_and_duplicate_submission_guard_are_persistent(tmp_path):
    store = ProductStore(tmp_path / "product.sqlite3")
    store.create_mission("m1", "Test")
    store.create_run("r1", "m1", "R1", "hash")
    store.create_run("r2", "m1", "R2", "hash")
    store.add_artifact("a1", "r1", "orthophoto", "out/ortho.tif", sha256="abc")
    store.add_evidence("e1", "a1", "hash", "manifest", "Verified")
    store.claim_submission("r1", "input-hash-options")
    store.claim_submission("r1", "input-hash-options")
    with pytest.raises(ValueError): store.claim_submission("r2", "input-hash-options")
    store.attach_webodm_task("r1", "task-1")
    store.attach_webodm_task("r1", "task-1")
    with pytest.raises(ValueError): store.attach_webodm_task("r1", "task-2")
    reopened = ProductStore(tmp_path / "product.sqlite3")
    assert reopened.list_artifacts("r1")[0]["sha256"] == "abc"
    assert reopened.list_evidence("a1")[0]["status"] == "Verified"

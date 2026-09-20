import json
import time

from astrakriti3d.orchestrator import PreparationQueue


def test_preparation_queue_is_async_and_persistent(tmp_path, monkeypatch):
    calls = []

    def prepare(video, output, **kwargs):
        calls.append((video, output, kwargs))
        return {"project_report": {"image_count": 2, "route": "local_unreferenced"}}

    monkeypatch.setattr("astrakriti3d.orchestrator.prepare_project", prepare)
    state = tmp_path / "queue.json"
    queue = PreparationQueue(state)
    queued = queue.submit("j1", tmp_path / "v.mp4", tmp_path / "out", mode="local")
    assert queued["status"] in {"queued", "running", "completed"}
    for _ in range(50):
        if queue.status("j1")["status"] == "completed":
            break
        time.sleep(0.01)
    assert queue.status("j1")["status"] == "completed"
    assert len(calls) == 1
    assert PreparationQueue(state).status("j1")["status"] == "completed"
    assert json.loads(state.read_text())["j1"]["result"]["image_count"] == 2

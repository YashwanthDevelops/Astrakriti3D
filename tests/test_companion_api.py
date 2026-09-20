import io
import zipfile

from astrakriti3d.companion_api import create_companion_app


class FakePreparationQueue:
    def __init__(self):
        self.jobs = {}
        self.submits = 0

    def submit(self, job_id, video, output, *, mode, srt=None, **options):
        self.submits += 1
        self.jobs[job_id] = {
            "status": "queued",
            "created_at": "now",
            "video": str(video),
            "output": str(output),
            "mode": mode,
            "srt": str(srt) if srt else None,
        }
        return self.status(job_id)

    def status(self, job_id):
        if job_id not in self.jobs:
            raise KeyError(job_id)
        return dict(self.jobs[job_id])

    def cancel(self, job_id):
        job = self.jobs[job_id]
        job["status"] = "cancelled"
        return self.status(job_id)


def upload(video=b"video", srt=None, job_id="submission-00000001", mode="local"):
    data = {
        "job_id": job_id,
        "mode": mode,
        "video": (io.BytesIO(video), "capture.mp4"),
    }
    if srt is not None:
        data["srt"] = (io.BytesIO(srt), "capture.srt")
    return data


def test_companion_requires_bearer_token_and_does_not_expose_service_without_it(tmp_path):
    app = create_companion_app(root=tmp_path, token="secret", queue=FakePreparationQueue())
    client = app.test_client()

    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    response = client.get("/health", headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ready",
        "service": "astrakriti-preparation",
        "preparation_only": True,
    }


def test_companion_preparation_is_idempotent_and_rejects_changed_inputs(tmp_path):
    queue = FakePreparationQueue()
    app = create_companion_app(root=tmp_path, token="secret", queue=queue)
    client = app.test_client()
    headers = {"Authorization": "Bearer secret"}

    first = client.post("/v1/preparations", data=upload(), headers=headers)
    second = client.post("/v1/preparations", data=upload(), headers=headers)
    changed = client.post(
        "/v1/preparations", data=upload(video=b"different"), headers=headers
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.get_json()["job_id"] == first.get_json()["job_id"]
    assert queue.submits == 1
    assert changed.status_code == 400
    assert "different video" in changed.get_json()["detail"]


def test_companion_bundle_contains_only_prepared_output(tmp_path):
    queue = FakePreparationQueue()
    app = create_companion_app(root=tmp_path, token="secret", queue=queue)
    client = app.test_client()
    headers = {"Authorization": "Bearer secret"}
    job_id = "submission-00000002"
    response = client.post("/v1/preparations", data=upload(job_id=job_id), headers=headers)
    assert response.status_code == 202

    record = app.config["ASTRAKRITI_COMPANION_ROOT"] / "jobs" / job_id / "prepared"
    record.mkdir(parents=True)
    (record / "manifest.json").write_text('{"frames": []}', encoding="utf-8")
    (record / "frames").mkdir()
    (record / "frames" / "frame.jpg").write_bytes(b"frame")
    queue.jobs[job_id]["status"] = "completed"

    bundle = client.get(
        "/v1/preparations/{}/bundle".format(job_id), headers=headers
    )
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.data)) as archive:
        assert set(archive.namelist()) == {"frames/frame.jpg", "manifest.json"}

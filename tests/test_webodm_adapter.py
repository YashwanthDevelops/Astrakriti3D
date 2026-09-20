from pathlib import Path

from integrations.webodm_adapter import WebODMAdapter


class FakeClient:
    class Response:
        def json(self):
            return [{"id": "node-1", "online": True}]

    def request(self, method, path):
        assert (method, path) == ("GET", "/processingnodes/")
        return self.Response()

    def find_or_create_project(self):
        return "p1"

    def submit_task(self, project_id, manifest, options, geo_txt=None):
        assert project_id == "p1"
        assert len(manifest) == 1
        return "t1"

    def task(self, project_id, task_id):
        return {"status": 30, "progress": "42.5"}

    def cancel(self, project_id, task_id):
        self.cancelled = (project_id, task_id)

    def download(self, project_id, task_id, asset, destination):
        return Path(destination)


def test_adapter_exposes_product_facing_operations_without_client_details(tmp_path):
    adapter = WebODMAdapter(FakeClient())
    assert adapter.create_project() == "p1"
    assert adapter.create_task("p1", [{"path": "frame.jpg"}], []) == "t1"
    status = adapter.get_task_status("p1", "t1")
    assert status.task_id == "t1"
    assert status.state == "30"
    assert status.progress == 42.5
    assert adapter.get_assets("p1", "t1", ["orthophoto.tif"], tmp_path) == [tmp_path / "orthophoto.tif"]
    assert adapter.health_check() is True

import hashlib
import json
from pathlib import Path

import pytest

from astrakriti3d.project import ProjectPreparationError, prepare_project


def _fake_prepare(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    frames = tmp_path / "out" / "frames"
    frames.mkdir(parents=True)
    records = []
    for i, ts in enumerate((0.0, 1.0), 1):
        p = frames / f"frame_{i:06d}.jpg"
        p.write_bytes(b"jpeg-" + bytes([i]))
        records.append({"output_filename": p.name, "output_path": str(p.resolve()), "source_timestamp_seconds": ts, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "dimensions": {"width": 4, "height": 3}})
    manifest = {"frames": records, "output_count": 2, "video": {"duration_seconds": 2.0}}
    def fake(video_path, output, **kwargs):
        out = Path(output)
        (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return manifest
    monkeypatch.setattr("astrakriti3d.project.prepare_video", fake)
    return video, tmp_path / "out"


def _srt(path, valid=True):
    body = "1\n00:00:00,000 --> 00:00:00,100\n[latitude: 1.0] [longitude: 2.0] [altitude: 4.0]\n\n2\n00:00:01,000 --> 00:00:01,100\n[latitude: 1.1] [longitude: 2.1] [altitude: 4.0]\n"
    if not valid:
        body = body.replace("[longitude: 2.0]", "[longitude: bad]")
    path.write_text(body, encoding="utf-8")


def test_video_only_local_reconstruction_has_no_geographic_inputs(tmp_path, monkeypatch):
    video, out = _fake_prepare(monkeypatch, tmp_path)
    result = prepare_project(video, out, mode="local")
    assert result["mode"] == "local"
    assert not (out / "geo.txt").exists()
    assert not (out / "telemetry").exists()
    report = json.loads((out / "project_report.json").read_text())
    assert report["absolute_position_available"] is False
    assert report["crs"] is None


def test_video_plus_srt_georeferenced_reconstruction(tmp_path, monkeypatch):
    video, out = _fake_prepare(monkeypatch, tmp_path)
    srt = tmp_path / "video.SRT"
    _srt(srt)
    result = prepare_project(video, out, mode="georeferenced", srt=srt)
    assert result["mode"] == "georeferenced"
    assert (out / "geo.txt").read_text().startswith("EPSG:4326\n")
    assert json.loads((out / "manifest.json").read_text())["mode"] == "georeferenced"


def test_missing_srt_in_georeferenced_mode_is_actionable(tmp_path, monkeypatch):
    video, out = _fake_prepare(monkeypatch, tmp_path)
    with pytest.raises(ProjectPreparationError, match="requires --srt"):
        prepare_project(video, out, mode="georeferenced")


def test_malformed_srt_is_rejected_in_georeferenced_mode(tmp_path, monkeypatch):
    video, out = _fake_prepare(monkeypatch, tmp_path)
    srt = tmp_path / "bad.SRT"
    _srt(srt, valid=False)
    with pytest.raises(ProjectPreparationError, match="invalid SRT/telemetry"):
        prepare_project(video, out, mode="georeferenced", srt=srt)


def test_local_mode_ignores_present_srt_and_never_creates_geo(tmp_path, monkeypatch):
    video, out = _fake_prepare(monkeypatch, tmp_path)
    srt = tmp_path / "bad.SRT"
    _srt(srt, valid=False)
    result = prepare_project(video, out, mode="local", srt=srt)
    assert result["mode"] == "local"
    assert not (out / "geo.txt").exists()
    assert not (out / "telemetry").exists()


def test_r2_diagnostics_are_path_free_advisory_and_preserve_r1_frames(tmp_path, monkeypatch):
    video, out = _fake_prepare(monkeypatch, tmp_path)

    def diagnostic(manifest_path, frames_dir, output, **options):
        assert options["dry_run"] is True
        assert Path(manifest_path).is_file()
        return {
            "candidate_count": 2,
            "selected_count": 1,
            "configuration": {"algorithm": "experimental", "selection_report": "private/path"},
            "rows": [
                {"frame_number": 1, "timestamp": 0, "blur_score": 3.2, "decision": "keep", "source_path": "private/path"},
                {"frame_number": 2, "timestamp": 1, "blur_score": 2.1, "decision": "reject", "source_path": "private/path"},
            ],
        }

    monkeypatch.setattr("astrakriti3d.project.adaptive_select_frames", diagnostic)
    prepare_project(video, out, mode="local")
    advisory = json.loads((out / "selection" / "advisory.json").read_text())
    assert advisory["baseline"] == "R1"
    assert advisory["policy"] == "advisory_only_all_source_frames_retained"
    assert "source_path" not in json.dumps(advisory)
    assert "private/path" not in json.dumps(advisory)
    assert sorted(p.name for p in (out / "frames").glob("*.jpg")) == ["frame_000001.jpg", "frame_000002.jpg"]


def test_selection_diagnostic_failure_does_not_fail_preparation(tmp_path, monkeypatch):
    video, out = _fake_prepare(monkeypatch, tmp_path)

    def unavailable(*args, **kwargs):
        raise RuntimeError("selector unavailable")

    monkeypatch.setattr("astrakriti3d.project.adaptive_select_frames", unavailable)
    result = prepare_project(video, out, mode="local")
    advisory = json.loads((out / "selection" / "advisory.json").read_text())
    assert result["mode"] == "local"
    assert advisory["status"] == "unavailable"
    assert "RuntimeError" in advisory["detail"]
    assert sorted(p.name for p in (out / "frames").glob("*.jpg")) == ["frame_000001.jpg", "frame_000002.jpg"]


def test_georeferenced_coverage_is_advisory_and_does_not_rewrite_geo_or_frames(tmp_path, monkeypatch):
    video, out = _fake_prepare(monkeypatch, tmp_path)
    srt = tmp_path / "video.SRT"
    _srt(srt)
    metrics = {
        "blur_score": 100.0,
        "clipped_ratio": 0.0,
        "feature_count": 200,
        "useful_match_count": 100,
        "match_ratio": 0.5,
        "median_feature_displacement": 20.0,
        "new_feature_ratio": 0.3,
        "image_similarity": 0.7,
    }
    monkeypatch.setattr(
        "astrakriti3d.selection._adaptive_metrics",
        lambda *args, **kwargs: (metrics, ([], None), None),
    )
    prepare_project(video, out, mode="georeferenced", srt=srt)
    original_geo = (out / "geo.txt").read_bytes()
    original_frames = {p.name: p.read_bytes() for p in (out / "frames").glob("*.jpg")}
    advisory = json.loads((out / "selection" / "advisory.json").read_text())
    assert "coverage" in advisory, advisory
    coverage = advisory["coverage"]
    assert coverage["status"] == "available"
    assert coverage["geo_validation"]["names_match"] is True
    assert len(coverage["rows"]) == 2
    assert (out / "geo.txt").read_bytes() == original_geo
    assert {p.name: p.read_bytes() for p in (out / "frames").glob("*.jpg")} == original_frames


def test_stale_geo_is_rejected_instead_of_reused(tmp_path, monkeypatch):
    video, out = _fake_prepare(monkeypatch, tmp_path)
    (out / "geo.txt").write_text("EPSG:4326\nold.jpg 1 2\n")
    with pytest.raises(ProjectPreparationError, match="stale telemetry"):
        prepare_project(video, out, mode="local")


def test_local_webodm_submission_omits_geo_txt(tmp_path):
    from astrakriti3d.config import Config
    from astrakriti3d.runner import run
    images = tmp_path / "images"
    images.mkdir()
    (images / "a.jpg").write_bytes(b"a")
    (images / "b.jpg").write_bytes(b"b")
    submitted = []
    class Client:
        def authenticate(self): pass
        def find_or_create_project(self): return "p"
        def submit_task(self, project, manifest, options, geo_txt=None):
            submitted.append(geo_txt)
            return "t"
        def task(self, project, task): return {"status": 40, "available_assets": []}
    result = run(Config("http://fake", "u", "p", poll_interval=0, db_path=tmp_path / "jobs.sqlite"), images, tmp_path / "run", client=Client(), mode="local")
    assert result["ok"] and result["mode"] == "local" and submitted == [None]

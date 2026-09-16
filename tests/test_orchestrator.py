import json
from pathlib import Path
import pytest

from astrakriti3d.orchestrator import run_pipeline


def _video(tmp_path):
    p = tmp_path / "video.mp4"; p.write_bytes(b"video"); return p


def _prepare(video, output, **kwargs):
    output.mkdir(parents=True)
    frames = output / "frames"; frames.mkdir()
    rows=[]
    for i, ts in enumerate((0.0, 1.0), 1):
        name=f"frame_{i:06d}.jpg"; (frames/name).write_bytes(b"jpg")
        rows.append({"output_filename":name,"source_timestamp_seconds":ts})
    (output/"manifest.json").write_text(json.dumps({"frames":rows}), encoding="utf-8")
    return {"mode":kwargs["mode"],"manifest":{"frames":rows},"project_report":{"image_count":2}}


def _preflight(*args, **kwargs): return {"status":"PASS"}


def _reconstruct(*args, **kwargs): return {"ok":True,"task_id":"task"}


def test_run_local_orchestrates_without_submitting_real_webodm(tmp_path):
    r=run_pipeline(_video(tmp_path),tmp_path/"run",mode="local",preflight_fn=_preflight,prepare_fn=_prepare,reconstruct_fn=_reconstruct)
    assert r["ok"] and r["prepared_input"]["frame_count"]==2


def test_run_georeferenced_passes_srt_and_geo(tmp_path):
    seen={}
    def prepare(video, output, **kwargs):
        seen.update(kwargs); result=_prepare(video,output,**kwargs); (output/"geo.txt").write_text("EPSG:4326\n",encoding="utf-8"); return result
    def reconstruct(video, images, output, **kwargs):
        seen["reconstruct"] = kwargs; return {"ok":True}
    srt=tmp_path/"video.srt"; srt.write_text("srt")
    r=run_pipeline(_video(tmp_path),tmp_path/"run",mode="georeferenced",srt=srt,preflight_fn=_preflight,prepare_fn=prepare,reconstruct_fn=reconstruct)
    assert r["ok"] and seen["mode"]=="georeferenced" and seen["reconstruct"]["geo_txt"].endswith("geo.txt")


def test_run_preflight_failure_stops_before_prepare_or_reconstruct(tmp_path):
    called=[]
    r=run_pipeline(_video(tmp_path),tmp_path/"run",mode="local",preflight_fn=lambda *a,**k:{"status":"FAIL"},prepare_fn=lambda *a,**k:called.append("prepare"),reconstruct_fn=lambda *a,**k:called.append("reconstruct"))
    assert not r["ok"] and r["stage"]=="preflight" and called==[]


def test_run_preparation_failure_stops_reconstruction(tmp_path):
    called=[]
    r=run_pipeline(_video(tmp_path),tmp_path/"run",mode="local",preflight_fn=_preflight,prepare_fn=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("extract failed")),reconstruct_fn=lambda *a,**k:called.append(1))
    assert not r["ok"] and r["stage"]=="preparation" and called==[]


def test_run_reconstruction_failure_is_nonzero_result(tmp_path):
    r=run_pipeline(_video(tmp_path),tmp_path/"run",mode="local",preflight_fn=_preflight,prepare_fn=_prepare,reconstruct_fn=lambda *a,**k:{"ok":False,"failure_report":{"category":"texrecon"}})
    assert not r["ok"] and r["stage"]=="reconstruction"


def test_run_cancellation_is_propagated(tmp_path):
    seen={}
    def reconstruct(*args,**kwargs): seen.update(kwargs); return {"ok":False,"cancelled":True}
    r=run_pipeline(_video(tmp_path),tmp_path/"run",mode="local",preflight_fn=_preflight,prepare_fn=_prepare,reconstruct_fn=reconstruct,cancel_after=1,poll_seconds=0)
    assert not r["ok"] and seen["cancel_after"]==1


def test_run_rejects_duplicate_output_before_stages(tmp_path):
    out=tmp_path/"run"; out.mkdir(); (out/"old.json").write_text("old")
    called=[]
    with pytest.raises(Exception, match="output already exists"):
        run_pipeline(_video(tmp_path),out,mode="local",preflight_fn=lambda *a,**k:called.append(1))
    assert not called

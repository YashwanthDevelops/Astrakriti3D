import json, hashlib
from pathlib import Path
import pytest
from astrakriti3d.baseline import BaselineError, inventory_baseline

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

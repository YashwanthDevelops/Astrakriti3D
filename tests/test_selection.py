import json, hashlib
from pathlib import Path
import pytest
from astrakriti3d.selection import SelectionError,select_frames

def fixture(tmp_path):
    frames=tmp_path/'frames'; frames.mkdir(); rows=[]
    for i,content in enumerate((b'a',b'a',b'b',b'c'),1):
        p=frames/f'frame_{i:06d}.jpg'; p.write_bytes(content); rows.append({'output_filename':p.name,'output_path':str(p),'source_timestamp_seconds':float(i-1),'source_frame_index':i-1,'sha256':hashlib.sha256(content).hexdigest()})
    m=tmp_path/'manifest.json'; m.write_text(json.dumps({'frames':rows})); return m,frames

def test_deterministic_selection_and_source_preserved(tmp_path):
    m,frames=fixture(tmp_path); a=select_frames(m,frames,tmp_path/'a',min_blur=0,duplicate_threshold=0,feature_floor=0); b=select_frames(m,frames,tmp_path/'b',min_blur=0,duplicate_threshold=0,feature_floor=0)
    assert [(x['output_filename'],x['sha256']) for x in a['frames']]==[(x['output_filename'],x['sha256']) for x in b['frames']]
    assert all(p.is_file() for p in frames.iterdir())

def test_invalid_threshold_rejected(tmp_path):
    m,frames=fixture(tmp_path)
    with pytest.raises(SelectionError): select_frames(m,frames,tmp_path/'out',duplicate_threshold=-1)

def test_manifest_decisions_and_protected_endpoints(tmp_path):
    m,frames=fixture(tmp_path); r=select_frames(m,frames,tmp_path/'out',min_blur=0,duplicate_threshold=100,feature_floor=0,continuity_seconds=100)
    assert r['diagnostics'][0]['decision']=='keep' and r['diagnostics'][-1]['decision']=='keep'
    assert all('source_sha256' in x for x in r['diagnostics'])

import json, hashlib
import pytest
from PIL import Image
from astrakriti3d.selection import select_frames, SelectionError
from astrakriti3d.resources import configure_threads, require_memory

def _fixture(tmp_path, count=4):
    d=tmp_path/'frames'; d.mkdir(parents=True); rows=[]
    for i in range(count):
        p=d/f'frame_{i+1:06d}.jpg'; Image.new('RGB',(64,48),(i*30,20,10)).save(p)
        rows.append({'output_filename':p.name,'output_path':str(p),'source_timestamp_seconds':float(i),'source_frame_index':i,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    m=tmp_path/'manifest.json'; m.write_text(json.dumps({'frames':rows})); return m,d

def test_frame_list_validation_rejects_duplicate_and_missing(tmp_path):
    m,d=_fixture(tmp_path); data=json.loads(m.read_text()); data['frames'][1]['output_filename']=data['frames'][0]['output_filename']; m.write_text(json.dumps(data))
    with pytest.raises(SelectionError,match='unique'): select_frames(m,d,tmp_path/'out')
    m,d=_fixture(tmp_path/'missing'); data=json.loads(m.read_text()); data['frames'][1]['output_path']=str(d/'absent.jpg'); m.write_text(json.dumps(data))
    with pytest.raises(SelectionError,match='missing source'): select_frames(m,d,tmp_path/'out2')

def test_deterministic_selection_and_quality_redundancy_metadata(tmp_path):
    m,d=_fixture(tmp_path); a=select_frames(m,d,tmp_path/'a',min_blur=0,duplicate_threshold=0,feature_floor=0); b=select_frames(m,d,tmp_path/'b',min_blur=0,duplicate_threshold=0,feature_floor=0)
    assert a['deterministic'] and [x['output_filename'] for x in a['frames']]==[x['output_filename'] for x in b['frames']]
    assert all('diagnostics' in x and 'decision' in x for x in a['diagnostics'])
    assert (tmp_path/'a'/'selection_timing.json').is_file()

def test_thread_configuration_is_bounded_and_memory_failure_is_explicit():
    assert configure_threads(2)==2
    with pytest.raises(ValueError): configure_threads(0)
    with pytest.raises(MemoryError,match='insufficient available memory'): require_memory(10**18,1)

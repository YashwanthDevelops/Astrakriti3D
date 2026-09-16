import hashlib, json
from PIL import Image
from astrakriti3d import selection

def _fixture(tmp_path, count=5):
    frames=tmp_path/'frames'; frames.mkdir(); rows=[]
    for i in range(count):
        p=frames/f'frame_{i+1:06d}.jpg'; Image.new('RGB',(32,24),(i*20,40,80)).save(p)
        rows.append({'output_filename':p.name,'output_path':str(p),'source_timestamp_seconds':float(i),'source_frame_index':i,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    manifest=tmp_path/'manifest.json'; manifest.write_text(json.dumps({'frames':rows})); return manifest,frames

def _fake(metrics):
    def run(path, previous=None, previous_features=None, cfg=None):
        i=int(path.stem.split('_')[-1]); return metrics.get(i,metrics[0]), ([],None), None
    return run

def test_adaptive_keeps_endpoints_and_rejects_redundant(tmp_path, monkeypatch):
    m,d=_fixture(tmp_path)
    base={'blur_score':100.0,'clipped_ratio':0.0,'feature_count':200,'useful_match_count':100,'match_ratio':.5,'median_feature_displacement':0.0,'new_feature_ratio':0.0,'image_similarity':1.0}
    monkeypatch.setattr(selection,'_adaptive_metrics',_fake({0:base,1:base,2:base,3:base,4:base}))
    r=selection.adaptive_select_frames(m,d,tmp_path/'out',target_fps=2,max_gap_seconds=10)
    assert [x['output_filename'] for x in r['frames']]==['frame_000001.jpg','frame_000005.jpg']

def test_adaptive_keeps_high_displacement_and_enforces_gap(tmp_path, monkeypatch):
    m,d=_fixture(tmp_path)
    base={'blur_score':100.0,'clipped_ratio':0.0,'feature_count':200,'useful_match_count':100,'match_ratio':.5,'median_feature_displacement':20.0,'new_feature_ratio':.3,'image_similarity':.7}
    monkeypatch.setattr(selection,'_adaptive_metrics',_fake({0:base,1:base,2:base,3:base,4:base}))
    r=selection.adaptive_select_frames(m,d,tmp_path/'out',target_fps=2,max_gap_seconds=2)
    assert r['selected_count'] >= 3
    assert all(b['timestamp']-a['timestamp'] <= 2 for a,b in zip(r['rows'],r['rows'][1:]) if a['decision']=='keep' and b['decision']=='keep')

def test_adaptive_dry_run_does_not_copy_source_or_change_determinism(tmp_path, monkeypatch):
    m,d=_fixture(tmp_path); before={p.name:p.read_bytes() for p in d.iterdir()}
    base={'blur_score':100.0,'clipped_ratio':0.0,'feature_count':200,'useful_match_count':100,'match_ratio':.5,'median_feature_displacement':0.0,'new_feature_ratio':0.0,'image_similarity':1.0}
    monkeypatch.setattr(selection,'_adaptive_metrics',_fake({0:base,1:base,2:base,3:base,4:base}))
    a=selection.adaptive_select_frames(m,d,tmp_path/'a',dry_run=True,target_fps=2,max_gap_seconds=10)
    b=selection.adaptive_select_frames(m,d,tmp_path/'b',dry_run=True,target_fps=2,max_gap_seconds=10)
    assert not (tmp_path/'a'/'frames').exists() and a['frames']==b['frames']
    assert {p.name:p.read_bytes() for p in d.iterdir()}==before

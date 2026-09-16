import json, hashlib
from pathlib import Path
import pytest
from astrakriti3d import video

def test_missing_video():
    with pytest.raises(video.VideoPreparationError,match="does not exist"): video.inspect_video("missing.mp4")
def test_unsupported_input(tmp_path):
    p=tmp_path/'x.txt'; p.write_text('x')
    with pytest.raises(video.VideoPreparationError,match="unsupported"): video.inspect_video(p)
def test_missing_ffprobe(tmp_path,monkeypatch):
    p=tmp_path/'x.mp4'; p.write_bytes(b'x'); monkeypatch.setattr(video.shutil,'which',lambda x:None)
    with pytest.raises(video.VideoPreparationError,match="ffprobe is unavailable"): video.inspect_video(p)
def test_malformed_probe(tmp_path,monkeypatch):
    p=tmp_path/'x.mp4'; p.write_bytes(b'x'); monkeypatch.setattr(video.shutil,'which',lambda x:'tool')
    monkeypatch.setattr(video,'_run',lambda cmd:type('R',(),{'returncode':0,'stdout':'{','stderr':''})())
    with pytest.raises(video.VideoPreparationError,match="malformed JSON"): video.inspect_video(p)
def fake_tools(monkeypatch):
    monkeypatch.setattr(video.shutil,'which',lambda x:'tool')
    probe={"streams":[{"index":0,"codec_type":"video","codec_name":"h264","width":4,"height":3,"duration":"2.0","time_base":"1/30","r_frame_rate":"30/1","tags":{"rotate":"90"}}],"format":{"duration":"2.0"}}
    lines="0|4|3\n0.5|4|3\n1.0|4|3\n1.5|4|3\n"
    class Proc:
        def __init__(self,*args,**kwargs): self.stdout=lines.splitlines(True); self.stderr=[]; self.returncode=0
        def __iter__(self): return iter(self.stdout)
        def read(self): return ''
        def read(self): return ''
        def poll(self): return self.returncode
        def wait(self,**kwargs): return 0
        def kill(self): self.returncode=-9
    monkeypatch.setattr(video.subprocess,'Popen',Proc)
    def run(cmd):
        out=json.dumps(probe)
        if cmd[0]=='ffmpeg': Path(cmd[-1]).write_bytes(b'frame-'+cmd[-1].encode()[-8:])
        return type('R',(),{'returncode':0,'stdout':out,'stderr':''})()
    monkeypatch.setattr(video,'_run',run)
    monkeypatch.setattr(video,'_jpeg_dimensions',lambda p:{'width':4,'height':3})
def test_prepare_manifest_monotonic_and_metadata(tmp_path,monkeypatch):
 fake_tools(monkeypatch); src=tmp_path/'v.mp4'; src.write_bytes(b'video'); r=video.prepare_video(src,tmp_path/'out',interval_seconds=1); assert [x['source_timestamp_seconds'] for x in r['frames']]==[0.0,1.0]; assert r['video']['rotation']=='90'; assert Path(tmp_path/'out/manifest.json').exists()
def test_repeated_preparation_deterministic(tmp_path,monkeypatch):
 fake_tools(monkeypatch); src=tmp_path/'v.mp4'; src.write_bytes(b'video'); a=video.prepare_video(src,tmp_path/'a',interval_seconds=1); fake_tools(monkeypatch); b=video.prepare_video(src,tmp_path/'b',interval_seconds=1); assert [(x['source_timestamp_seconds'],x['sha256']) for x in a['frames']]==[(x['source_timestamp_seconds'],x['sha256']) for x in b['frames']]
def test_hash_mismatch_detection(tmp_path,monkeypatch):
 fake_tools(monkeypatch); src=tmp_path/'v.mp4'; src.write_bytes(b'video'); video.prepare_video(src,tmp_path/'out'); p=tmp_path/'out/frames/frame_000001.jpg'; p.write_bytes(b'changed'); data=json.loads((tmp_path/'out/manifest.json').read_text()); assert hashlib.sha256(p.read_bytes()).hexdigest()!=data['frames'][0]['sha256']
def test_working_directory_independence(tmp_path,monkeypatch):
 fake_tools(monkeypatch); src=tmp_path/'v.mp4'; src.write_bytes(b'video'); old=Path.cwd(); import os; os.chdir(tmp_path); 
 try: r=video.prepare_video(src,tmp_path/'out'); assert r['output_count']==2
 finally: os.chdir(old)

def test_sequential_extraction_uses_one_ffmpeg_command_and_expected_count(tmp_path,monkeypatch):
    src=tmp_path/'v.mp4'; src.write_bytes(b'video'); frame_dir=tmp_path/'frames'; frame_dir.mkdir(); calls=[]
    def run(cmd,timeout=0):
        calls.append(cmd)
        for i in range(1,4): (frame_dir/f'frame_{i:06d}.jpg').write_bytes(b'jpeg')
        return type('R',(),{'returncode':0,'stdout':'','stderr':''})()
    monkeypatch.setattr(video,'_run',run)
    files=video._extract_sequential(src,frame_dir,.5,'ffmpeg',3)
    assert len(files)==3 and len(calls)==1 and '-vf' in calls[0] and 'fps=1/0.5' in calls[0]

def test_invalid_extraction_mode_rejected(tmp_path,monkeypatch):
    fake_tools(monkeypatch); src=tmp_path/'v.mp4'; src.write_bytes(b'video')
    with pytest.raises(video.VideoPreparationError,match='extraction_mode'):
        video.prepare_video(src,tmp_path/'out',extraction_mode='invalid')

def test_stream_parser_rejects_missing_timestamp(monkeypatch,tmp_path):
    class Proc:
        def __init__(self,*args,**kwargs): pass
        stdout=['|4|3\n']; stderr=[]; returncode=0
        def __iter__(self): return iter(self.stdout)
        def read(self): return ''
        def poll(self): return 0
        def wait(self,**kwargs): return 0
        def kill(self): pass
    monkeypatch.setattr(video.subprocess,'Popen',Proc); monkeypatch.setattr(video.shutil,'which',lambda x:'tool')
    with pytest.raises(video.VideoPreparationError,match='missing timestamp'): list(video.iter_frame_timestamps(tmp_path/'x.mp4'))

def test_stream_parser_rejects_malformed_timestamp(monkeypatch,tmp_path):
    class Proc:
        def __init__(self,*args,**kwargs): pass
        stdout=['wat|4|3\n']; stderr=[]; returncode=0
        def __iter__(self): return iter(self.stdout)
        def read(self): return ''
        def poll(self): return 0
        def wait(self,**kwargs): return 0
        def kill(self): pass
    monkeypatch.setattr(video.subprocess,'Popen',Proc)
    with pytest.raises(video.VideoPreparationError,match='malformed timestamp'): list(video.iter_frame_timestamps(tmp_path/'x.mp4'))

def test_stream_parser_variable_rate_and_nonzero_start(monkeypatch,tmp_path):
    class Proc:
        def __init__(self,*args,**kwargs): pass
        stdout=['2.5|4|3\n','2.7|4|3\n','3.9|4|3\n']; stderr=[]; returncode=0
        def __iter__(self): return iter(self.stdout)
        def poll(self): return 0
        def wait(self,**kwargs): return 0
        def kill(self): pass
    monkeypatch.setattr(video.subprocess,'Popen',Proc)
    assert [x['source_timestamp_seconds'] for x in video.iter_frame_timestamps(tmp_path/'x.mp4')]==[2.5,2.7,3.9]

def test_jpeg_dimensions(tmp_path):
    p=tmp_path/'x.jpg'; p.write_bytes(bytes.fromhex('ffd8ffc0001108000300040301110002110003011100ffd9'))
    assert video._jpeg_dimensions(p)=={'width':4,'height':3}

def test_streaming_timestamp_parsing(tmp_path, monkeypatch):
    yielded = []
    def line_generator():
        for t in [0.0, 0.5, 1.0]:
            yielded.append(t)
            yield f"{t}|1920|1080\n"
    class Proc:
        def __init__(self, *args, **kwargs):
            self.stdout = line_generator(); self.stderr = []; self.returncode = 0
        def __iter__(self): return self.stdout
        def poll(self): return 0
        def wait(self, **kwargs): return 0
        def kill(self): pass
    monkeypatch.setattr(video.subprocess, 'Popen', Proc)
    gen = video.iter_frame_timestamps(tmp_path / 'v.mp4')
    first = next(gen)
    assert first['source_timestamp_seconds'] == 0.0
    assert first['width'] == 1920 and first['height'] == 1080
    assert len(yielded) == 1

def test_variable_frame_rate_timestamps(tmp_path, monkeypatch):
    fake_tools(monkeypatch)
    vfr_lines = "0.0|4|3\n0.4|4|3\n0.9|4|3\n1.2|4|3\n1.8|4|3\n2.1|4|3\n3.5|4|3\n"
    class Proc:
        def __init__(self, *args, **kwargs):
            self.stdout = vfr_lines.splitlines(True); self.stderr = []; self.returncode = 0
        def __iter__(self): return iter(self.stdout)
        def poll(self): return 0
        def wait(self, **kwargs): return 0
        def kill(self): pass
    monkeypatch.setattr(video.subprocess, 'Popen', Proc)
    probe = {"streams":[{"index":0,"codec_type":"video","codec_name":"h264","width":4,"height":3,"duration":"4.0","time_base":"1/30","r_frame_rate":"30/1"}],"format":{"duration":"4.0"}}
    def run(cmd):
        if cmd[0] == 'ffmpeg': Path(cmd[-1]).write_bytes(b'frame-vfr')
        return type('R', (), {'returncode': 0, 'stdout': json.dumps(probe), 'stderr': ''})()
    monkeypatch.setattr(video, '_run', run)
    src = tmp_path / 'vfr.mp4'; src.write_bytes(b'dummy')
    res = video.prepare_video(src, tmp_path / 'vfr_out', interval_seconds=1.0)
    selected = [f['source_timestamp_seconds'] for f in res['frames']]
    assert selected == [0.0, 1.2, 2.1, 3.5]

def test_nonzero_stream_start_time(tmp_path, monkeypatch):
    fake_tools(monkeypatch)
    start_lines = "2.5|4|3\n2.8|4|3\n3.1|4|3\n3.9|4|3\n4.2|4|3\n"
    class Proc:
        def __init__(self, *args, **kwargs):
            self.stdout = start_lines.splitlines(True); self.stderr = []; self.returncode = 0
        def __iter__(self): return iter(self.stdout)
        def poll(self): return 0
        def wait(self, **kwargs): return 0
        def kill(self): pass
    monkeypatch.setattr(video.subprocess, 'Popen', Proc)
    probe = {"streams":[{"index":0,"codec_type":"video","codec_name":"h264","width":4,"height":3,"duration":"5.0","time_base":"1/30","r_frame_rate":"30/1"}],"format":{"duration":"5.0"}}
    def run(cmd):
        if cmd[0] == 'ffmpeg': Path(cmd[-1]).write_bytes(b'frame-nonzero')
        return type('R', (), {'returncode': 0, 'stdout': json.dumps(probe), 'stderr': ''})()
    monkeypatch.setattr(video, '_run', run)
    src = tmp_path / 'nonzero.mp4'; src.write_bytes(b'dummy')
    res = video.prepare_video(src, tmp_path / 'nonzero_out', interval_seconds=1.0)
    selected = [f['source_timestamp_seconds'] for f in res['frames']]
    assert selected == [2.5, 3.1, 4.2]

def test_stream_parser_rejects_nan_and_inf(monkeypatch, tmp_path):
    class Proc:
        def __init__(self, *args, **kwargs): pass
        stdout = ['nan|4|3\n']; stderr = []; returncode = 0
        def __iter__(self): return iter(self.stdout)
        def poll(self): return 0
        def wait(self, **kwargs): return 0
        def kill(self): pass
    monkeypatch.setattr(video.subprocess, 'Popen', Proc)
    with pytest.raises(video.VideoPreparationError, match='invalid timestamp record'):
        list(video.iter_frame_timestamps(tmp_path / 'x.mp4'))

def test_rotation_and_actual_output_dimensions(tmp_path, monkeypatch):
    monkeypatch.setattr(video.shutil, 'which', lambda x: 'tool')
    probe = {"streams":[{"index":0,"codec_type":"video","codec_name":"h264","width":1920,"height":1080,"duration":"1.5","time_base":"1/30","r_frame_rate":"30/1","tags":{"rotate":"90"}}],"format":{"duration":"1.5"}}
    lines = "0.0|1920|1080\n1.0|1920|1080\n"
    class Proc:
        def __init__(self, *args, **kwargs): self.stdout = lines.splitlines(True); self.stderr = []; self.returncode = 0
        def __iter__(self): return iter(self.stdout)
        def poll(self): return 0
        def wait(self, **kwargs): return 0
        def kill(self): pass
    monkeypatch.setattr(video.subprocess, 'Popen', Proc)
    def run(cmd):
        if cmd[0] == 'ffmpeg': Path(cmd[-1]).write_bytes(b'frame-rotated')
        return type('R', (), {'returncode': 0, 'stdout': json.dumps(probe), 'stderr': ''})()
    monkeypatch.setattr(video, '_run', run)
    monkeypatch.setattr(video, '_jpeg_dimensions', lambda p: {'width': 1080, 'height': 1920})
    src = tmp_path / 'rot.mp4'; src.write_bytes(b'dummy')
    res = video.prepare_video(src, tmp_path / 'rot_out', interval_seconds=1.0)
    frame = res['frames'][0]
    assert frame['dimensions'] == {'width': 1080, 'height': 1920}
    assert frame['source_dimensions'] == {'width': 1920, 'height': 1080}
    assert frame['transformations']['rotation'] == '90'
    assert 'autorotation' in frame['transformations']['extraction']

def test_partial_extraction_and_subprocess_failure(tmp_path, monkeypatch):
    fake_tools(monkeypatch)
    src = tmp_path / 'fail.mp4'; src.write_bytes(b'dummy')
    out = tmp_path / 'fail_out'
    def failing_run(cmd):
        if cmd[0] == 'ffmpeg':
            Path(cmd[-1]).write_bytes(b'corrupt')
            return type('R', (), {'returncode': 1, 'stdout': '', 'stderr': 'simulated ffmpeg decoder fault'})()
        probe = {"streams":[{"index":0,"codec_type":"video","codec_name":"h264","width":4,"height":3,"duration":"2.0","time_base":"1/30","r_frame_rate":"30/1"}],"format":{"duration":"2.0"}}
        return type('R', (), {'returncode': 0, 'stdout': json.dumps(probe), 'stderr': ''})()
    monkeypatch.setattr(video, '_run', failing_run)
    with pytest.raises(video.VideoPreparationError, match="frame extraction failed at 0.000000s: simulated ffmpeg decoder fault"):
        video.prepare_video(src, out)
    assert not (out / 'frames' / 'frame_000001.jpg').exists()

def test_bounded_memory_behavior(tmp_path, monkeypatch):
    def big_stream():
        for i in range(50000):
            yield f"{i * 0.033:.3f}|1920|1080\n"
    class Proc:
        def __init__(self, *args, **kwargs):
            self.stdout = big_stream(); self.stderr = []; self.returncode = 0
        def __iter__(self): return self.stdout
        def poll(self): return 0
        def wait(self, **kwargs): return 0
        def kill(self): pass
    monkeypatch.setattr(video.subprocess, 'Popen', Proc)
    gen = video.iter_frame_timestamps(tmp_path / 'big.mp4')
    items = [next(gen) for _ in range(100)]
    assert len(items) == 100
    assert items[0]['source_frame_index'] == 0
    assert items[99]['source_frame_index'] == 99

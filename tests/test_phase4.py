import hashlib, json
from pathlib import Path
import pytest
from astrakriti3d.geolocation import GeolocationError, prepare_geolocation
from astrakriti3d.client import WebODMClient
from astrakriti3d.config import Config

def fixtures(tmp_path):
    src=tmp_path/'frame_000001.jpg'; src.write_bytes(b'jpeg-fixture')
    video=tmp_path/'v.mp4'; video.write_bytes(b'video')
    fm=tmp_path/'m.json'; fm.write_text(json.dumps({'frames':[{'output_filename':src.name,'output_path':str(src),'sha256':hashlib.sha256(src.read_bytes()).hexdigest()}]}))
    am=tmp_path/'a.json'; am.write_text(json.dumps({'rows':[{'frame_filename':src.name,'frame_timestamp_seconds':1.0,'matched_telemetry_timestamp_seconds':1.0,'signed_time_difference_seconds':0.0,'association_status':'matched','latitude':1.2,'longitude':-3.4,'altitude':50.0}]}))
    return video,fm,am,src

def test_geo_txt_route_readback_and_source_immutability(tmp_path):
    v,f,a,src=fixtures(tmp_path); before=src.read_bytes(); r=prepare_geolocation(v,f,a,tmp_path/'out')
    assert r['route']=='odm_geo_txt' and r['readback_verified']
    assert (tmp_path/'out/geo.txt').read_text()=='EPSG:4326\nframe_000001.jpg -3.400000000000 1.200000000000\n'
    assert src.read_bytes()==before
    assert r['projection']['coordinate_order']=='longitude latitude in geo.txt'

def test_invalid_and_unmatched_telemetry_rejected(tmp_path):
    v,f,a,src=fixtures(tmp_path); data=json.loads(a.read_text()); data['rows'][0]['association_status']='unmatched'; a.write_text(json.dumps(data))
    with pytest.raises(GeolocationError,match='not matched'): prepare_geolocation(v,f,a,tmp_path/'out')

def test_hash_mismatch_rejected(tmp_path):
    v,f,a,src=fixtures(tmp_path); src.write_bytes(b'changed')
    with pytest.raises(GeolocationError,match='hash mismatch'): prepare_geolocation(v,f,a,tmp_path/'out')

def test_webodm_multipart_includes_geo_txt(tmp_path):
    image=tmp_path/'a.jpg'; image.write_bytes(b'a'); geo=tmp_path/'geo.txt'; geo.write_text('EPSG:4326\na.jpg 2 1\n')
    class Response:
        status_code=201
        def json(self): return {'id':'task-1'}
        text=''
    class Session:
        def __init__(self): self.kwargs=None
        def request(self,method,url,**kwargs): self.kwargs=kwargs; return Response()
    session=Session(); client=WebODMClient(Config('http://fake','u','p'),session=session)
    task=client.submit_task('project',[{'name':'a.jpg','path':str(image)}],[],geo_txt=geo)
    assert task=='task-1'
    uploaded=[item[1][0] for item in session.kwargs['files']]
    assert uploaded==['a.jpg','geo.txt']

def test_runner_passes_geo_txt_and_multipart_submitted(tmp_path):
    from astrakriti3d.runner import run
    img_dir=tmp_path/'images'; img_dir.mkdir(); (img_dir/'a.jpg').write_bytes(b'fake-jpeg-1'); (img_dir/'b.jpg').write_bytes(b'fake-jpeg-2')
    geo=tmp_path/'geo.txt'; geo.write_text('EPSG:4326\na.jpg 36.8 0.3\nb.jpg 36.9 0.4\n')
    submitted_files=[]
    class FakeClient:
        def authenticate(self): pass
        def find_or_create_project(self): return 'p1'
        def submit_task(self,p,m,o,geo_txt=None):
            nonlocal submitted_files
            submitted_files=[x['name'] for x in m]
            if geo_txt: submitted_files.append(Path(geo_txt).name)
            return 't1'
        def task(self,p,t): return {'status':40,'available_assets':['orthophoto.tif']}
        def download(self,p,t,asset,dest): Path(dest).parent.mkdir(parents=True,exist_ok=True); Path(dest).write_bytes(b'data')
    client=FakeClient()
    r=run(Config('http://fake','u','p',poll_interval=0,db_path=tmp_path/'j.sqlite'),img_dir,tmp_path/'out',client=client,geo_txt=geo)
    assert r['ok']
    assert submitted_files==['a.jpg','b.jpg','geo.txt']

def test_runner_automatic_geo_txt_wiring(tmp_path):
    from astrakriti3d.runner import run
    img_dir=tmp_path/'images'; img_dir.mkdir(); (img_dir/'a.jpg').write_bytes(b'fake-jpeg-1'); (img_dir/'b.jpg').write_bytes(b'fake-jpeg-2')
    # Place geo.txt in parent directory without explicitly passing geo_txt argument
    (tmp_path/'geo.txt').write_text('EPSG:4326\na.jpg 36.8 0.3\nb.jpg 36.9 0.4\n')
    submitted_files=[]
    class FakeClient:
        def authenticate(self): pass
        def find_or_create_project(self): return 'p1'
        def submit_task(self,p,m,o,geo_txt=None):
            nonlocal submitted_files
            submitted_files=[x['name'] for x in m]
            if geo_txt: submitted_files.append(Path(geo_txt).name)
            return 't1'
        def task(self,p,t): return {'status':40,'available_assets':['orthophoto.tif']}
        def download(self,p,t,asset,dest): Path(dest).parent.mkdir(parents=True,exist_ok=True); Path(dest).write_bytes(b'data')
    client=FakeClient()
    r=run(Config('http://fake','u','p',poll_interval=0,db_path=tmp_path/'j.sqlite'),img_dir,tmp_path/'out',client=client)
    assert r['ok']
    assert 'geo.txt' in submitted_files

def test_runner_downloads_shots_geojson_and_parses_coordinates(tmp_path):
    from astrakriti3d.runner import run
    img_dir=tmp_path/'images'; img_dir.mkdir(); (img_dir/'a.jpg').write_bytes(b'fake-jpeg-1'); (img_dir/'b.jpg').write_bytes(b'fake-jpeg-2')
    geo=tmp_path/'geo.txt'; geo.write_text('EPSG:4326\na.jpg 36.8 0.3\nb.jpg 36.9 0.4\n')
    shots_payload=json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','properties':{'filename':'a.jpg'},'geometry':{'type':'Point','coordinates':[36.80001,0.30002,29.5]}}]})
    class FakeClient:
        def authenticate(self): pass
        def find_or_create_project(self): return 'p1'
        def submit_task(self,p,m,o,geo_txt=None): return 't1'
        def task(self,p,t): return {'status':40,'available_assets':['orthophoto.tif','shots.geojson','cameras.json']}
        def download(self,p,t,asset,dest):
            Path(dest).parent.mkdir(parents=True,exist_ok=True)
            if asset=='shots.geojson': Path(dest).write_text(shots_payload)
            else: Path(dest).write_bytes(b'dummy')
    client=FakeClient()
    r=run(Config('http://fake','u','p',poll_interval=0,db_path=tmp_path/'j.sqlite'),img_dir,tmp_path/'out',client=client,geo_txt=geo)
    assert r['ok']
    assert 'shots.geojson' in [a['name'] for a in r['artifacts']]
    assert r['camera_coordinates']['a.jpg']==[36.80001,0.30002,29.5]


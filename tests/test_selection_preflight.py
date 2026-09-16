import json
from pathlib import Path
from PIL import Image
from astrakriti3d.selection_preflight import validate_selection, classify_failure

def _jpg(path, color=(20,30,40), size=(32,24)):
    Image.new('RGB', size, color).save(path, format='JPEG')

def test_preflight_validates_exact_geo_membership_and_dimensions(tmp_path):
    _jpg(tmp_path/'a.jpg'); _jpg(tmp_path/'b.jpg', (50,60,70))
    geo=tmp_path/'geo.txt'; geo.write_text('EPSG:4326\na.jpg 36.8 0.3\nb.jpg 36.9 0.4\n')
    r=validate_selection(tmp_path, geo)
    assert r['valid'] and r['geo_names_match_images'] and r['uniform_dimensions']

def test_preflight_rejects_corrupt_and_bad_coordinate(tmp_path):
    _jpg(tmp_path/'a.jpg'); (tmp_path/'b.jpg').write_bytes(b'not-jpeg')
    geo=tmp_path/'geo.txt'; geo.write_text('EPSG:4326\na.jpg 181 0\nb.jpg 36.9 0.4\n')
    r=validate_selection(tmp_path, geo)
    assert not r['valid'] and any(x['kind']=='unreadable_image' for x in r['errors']) and any(x['kind']=='invalid_coordinate' for x in r['errors'])

def test_preflight_detects_dimension_and_geo_mismatch(tmp_path):
    _jpg(tmp_path/'a.jpg', size=(32,24)); _jpg(tmp_path/'b.jpg', size=(64,24))
    geo=tmp_path/'geo.txt'; geo.write_text('EPSG:4326\na.jpg 36.8 0.3\nextra.jpg 36.9 0.4\n')
    r=validate_selection(tmp_path, geo)
    assert not r['uniform_dimensions'] and any(x['kind']=='geo_image_membership' for x in r['errors'])

def test_failure_classification_is_explicit(tmp_path):
    log=tmp_path/'run.log'; log.write_text('Reconstruction 0: 185 images, 115869 points\n1 partial reconstructions in total.\nUndistorting\ncv2.error: Unknown C++ exception from OpenCV code')
    r=classify_failure(log, {'status':30}, [])
    assert r['classification']=='opencv_undistortion_exception' and r['partial_reconstruction']

def test_mixed_dimensions_alone_are_invalid(tmp_path):
    _jpg(tmp_path/'a.jpg'); _jpg(tmp_path/'b.jpg', size=(64,24))
    geo=tmp_path/'geo.txt'; geo.write_text('EPSG:4326\na.jpg 36 0\nb.jpg 36 0\n')
    r=validate_selection(tmp_path,geo)
    assert not r['valid'] and {'kind':'inconsistent_dimensions'} in r['errors']

def test_orientation_and_metadata_consistency_are_enforced(tmp_path):
    _jpg(tmp_path/'a.jpg')
    exif=Image.Exif(); exif[274]=6
    Image.new('RGB',(32,24)).save(tmp_path/'b.jpg',exif=exif)
    geo=tmp_path/'geo.txt'; geo.write_text('EPSG:4326\na.jpg 36 0\nb.jpg 36 0\n')
    r=validate_selection(tmp_path,geo)
    assert not r['valid'] and {'kind':'inconsistent_orientation'} in r['errors']

def test_truncated_jpeg_pixels_fail_even_with_readable_header(tmp_path):
    p=tmp_path/'a.jpg'; _jpg(p,size=(256,256)); p.write_bytes(p.read_bytes()[:-30])
    with Image.open(p) as im: im.verify()  # Header-only check misses this corruption.
    geo=tmp_path/'geo.txt'; geo.write_text('EPSG:4326\na.jpg 36 0\n')
    r=validate_selection(tmp_path,geo)
    assert not r['valid'] and any(x['kind']=='unreadable_image' for x in r['errors'])

def test_empty_selection_and_duplicate_content_are_invalid(tmp_path):
    geo=tmp_path/'geo.txt'; geo.write_text('EPSG:4326\n')
    assert not validate_selection(tmp_path,geo)['valid']
    _jpg(tmp_path/'a.jpg'); (tmp_path/'b.jpg').write_bytes((tmp_path/'a.jpg').read_bytes())
    geo.write_text('EPSG:4326\na.jpg 36 0\nb.jpg 36 0\n')
    assert not validate_selection(tmp_path,geo)['valid']

def test_original_traceback_classifies_thread_runtime_not_bad_image(tmp_path):
    log=tmp_path/'engine.log'
    log.write_text('Undistorting\nparallel_map\nthreads_used = cv2.getNumThreads()\ncv2.error: Unknown C++ exception from OpenCV code')
    r=classify_failure(log,{'status':30},[])
    assert r['classification']=='opencv_thread_runtime_exception'
    assert not r['root_cause_confirmed'] and not r['artifacts_present']

def test_task_submission_timeout_is_not_replayed():
    import requests
    from astrakriti3d.client import WebODMClient, WebODMError
    from astrakriti3d.config import Config
    class Session:
        calls=0
        def request(self,*args,**kwargs):
            self.calls+=1
            raise requests.Timeout()
    s=Session(); c=WebODMClient(Config('http://fake','u','p'),session=s)
    import pytest
    with pytest.raises(WebODMError): c.request('POST','/projects/1/tasks/')
    assert s.calls==1

def test_submission_rejects_duplicate_geo_and_missing_image(tmp_path):
    from astrakriti3d.client import WebODMClient, WebODMError
    from astrakriti3d.config import Config
    import pytest
    _jpg(tmp_path/'a.jpg'); _jpg(tmp_path/'b.jpg')
    geo=tmp_path/'geo.txt'; geo.write_text('EPSG:4326\na.jpg 36 0\na.jpg 36 0\n')
    c=WebODMClient(Config('http://fake','u','p'))
    with pytest.raises(WebODMError,match='identities exactly'):
        c.submit_task('1',[{'path':str(tmp_path/n)} for n in ('a.jpg','b.jpg')],[],geo_txt=geo)

def test_manifest_duplicate_identity_is_not_collapsed_silently(tmp_path):
    import hashlib
    _jpg(tmp_path/'a.jpg')
    geo=tmp_path/'geo.txt'; geo.write_text('EPSG:4326\na.jpg 36 0\n')
    frame={'output_filename':'a.jpg','source_sha256':hashlib.sha256((tmp_path/'a.jpg').read_bytes()).hexdigest()}
    manifest=tmp_path/'manifest.json'; manifest.write_text(json.dumps({'frames':[frame,frame]}))
    assert not validate_selection(tmp_path,geo,manifest)['valid']

def test_expired_poll_token_refreshes_without_resubmitting():
    from astrakriti3d.client import WebODMClient
    from astrakriti3d.config import Config
    class Response:
        def __init__(self,status,text): self.status_code=status; self.text=text
        def json(self): return json.loads(self.text)
    class Session:
        gets=0; authentications=0
        def request(self,method,url,**kwargs):
            assert method=='GET'
            self.gets+=1
            if self.gets==1: return Response(403,'{"detail":"Signature has expired."}')
            assert kwargs['headers']['Authorization']=='JWT refreshed'
            return Response(200,'{"status":40}')
        def post(self,url,**kwargs):
            assert url.endswith('/token-auth/')
            self.authentications+=1
            return Response(200,'{"token":"refreshed"}')
    s=Session(); c=WebODMClient(Config('http://fake','u','p'),session=s); c.token='expired'
    assert c.task('1','existing')['status']==40
    assert s.gets==2 and s.authentications==1

def test_one_partial_reconstruction_does_not_mean_fragmented_connectivity(tmp_path):
    p=tmp_path/'log'; p.write_text('1 partial reconstructions in total.\nunspecified engine failure')
    result=classify_failure(p,{'status':30})
    assert result['reconstruction_component_count']==1
    assert result['fragmented_reconstruction'] is False
    assert result['classification']=='engine_failure'

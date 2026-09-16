import json, threading, hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from astrakriti3d.config import Config
from astrakriti3d.client import WebODMClient
from astrakriti3d.storage import JobStore, manifest_for_images, fingerprint
from astrakriti3d.runner import run
from astrakriti3d.client import WebODMError, redact
import requests, subprocess, sys

class H(BaseHTTPRequestHandler):
    statuses=[10,20,40]; calls=[]
    def log_message(self,*a): pass
    def do_POST(self):
        H.calls.append((self.command,self.path)); n=int(self.headers.get('Content-Length',0)); self.rfile.read(n)
        if self.path.endswith('token-auth/'):
            self.send(200,{"token":"secret"})
        elif self.path.endswith('/projects/'):
            self.send(201,{"id":7})
        elif self.path.endswith('/tasks/'):
            self.send(201,{"id":8})
        elif self.path.endswith('/cancel/'):
            self.send(200,{})
        else: self.send(404,{})
    def do_GET(self):
        H.calls.append((self.command,self.path))
        if self.path.endswith('/projects/') : self.send(200,[])
        elif '/download/' in self.path: self.send_raw(200,b'artifact')
        elif '/output/' in self.path: self.send_raw(200,b'log line')
        else:
            self.send(200,{"id":8,"status":H.statuses.pop(0),"running_progress":1})
    def send(self,code,obj): self.send_raw(code,json.dumps(obj).encode(),"application/json")
    def send_raw(self,code,data,typ="application/octet-stream"):
        self.send_response(code); self.send_header('Content-Type',typ); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
def server():
 s=HTTPServer(('127.0.0.1',0),H); threading.Thread(target=s.serve_forever,daemon=True).start(); return s
def test_client_contract(tmp_path):
 s=server(); c=Config(f'http://127.0.0.1:{s.server_port}','u','p',timeout=2,poll_interval=0.001); x=WebODMClient(c); x.authenticate(); assert x.token=='secret'; assert x.find_or_create_project()=='7';
 p=tmp_path/'a.jpg'; q=tmp_path/'b.jpg'; p.write_bytes(b'a'); q.write_bytes(b'b'); m=manifest_for_images(tmp_path); assert x.submit_task('7',m,[])=='8'; d=x.download('7','8','orthophoto.tif',tmp_path/'x'); assert d.read_bytes()==b'artifact'; s.shutdown()
def test_persistence_restart(tmp_path):
    p=tmp_path/'a.jpg'; q=tmp_path/'b.jpg'; p.write_bytes(b'a'); q.write_bytes(b'b'); m=manifest_for_images(tmp_path); st=JobStore(tmp_path/'j.sqlite'); fp=fingerprint(m,[]); st.create('local',fp,m,[]); st.update('local',project_id='7',task_id='8',state='running',artifacts=[{'sha256':'x'}]); r=JobStore(tmp_path/'j.sqlite').get_by_fingerprint(fp); assert r['task_id']=='8' and json.loads(r['artifacts'])[0]['sha256']=='x'

class Fake:
    def __init__(self, statuses, fail=None): self.statuses=list(statuses); self.submits=0; self.cancels=0; self.fail=fail
    def authenticate(self): pass
    def find_or_create_project(self): return 'p1'
    def submit_task(self,p,m,o): self.submits+=1; return 't1'
    def task(self,p,t):
        if self.fail: return {"status":30,"last_error":self.fail}
        value=self.statuses.pop(0); return value if isinstance(value,dict) else {"status":value,"running_progress":0.5}
    def cancel(self,p,t): self.cancels+=1
    def download(self,p,t,a,d): Path(d).parent.mkdir(parents=True,exist_ok=True); Path(d).write_bytes(b'fixture'); return Path(d)

def images(tmp_path):
    (tmp_path/'a.jpg').write_bytes(b'a'); (tmp_path/'b.jpg').write_bytes(b'b'); return tmp_path

def test_polling_progress_and_artifact_hash(tmp_path):
    f=Fake([10,20,40]); r=run(Config('http://fake','u','p',poll_interval=0),images(tmp_path),tmp_path/'out',client=f); assert r['ok']; assert [e['status'] for e in r['events']]==['queued','running','completed']; assert r['artifact']['sha256']==hashlib.sha256(Path(r['artifact']['path']).read_bytes()).hexdigest()

def test_restart_reconciliation_no_duplicate_submission(tmp_path):
    f=Fake([40,40]); c=Config('http://fake','u','p',poll_interval=0,db_path=tmp_path/'jobs.sqlite'); r1=run(c,images(tmp_path),tmp_path/'o1',client=f); r2=run(c,images(tmp_path),tmp_path/'o2',client=f); assert r1['task_id']==r2['task_id']=='t1'; assert f.submits==1

def test_cancellation_is_observable(tmp_path):
    f=Fake([20]); r=run(Config('http://fake','u','p',poll_interval=0),images(tmp_path),tmp_path/'out',cancel_after=0,client=f); assert r['cancelled'] and not r['ok'] and f.cancels==1

def test_remote_failure_captures_diagnostics(tmp_path):
    r=run(Config('http://fake','u','p',db_path=tmp_path/'j.sqlite'),images(tmp_path),tmp_path/'out',client=Fake([],fail='out of memory')); assert not r['ok'] and 'out of memory' in r['error']['message']

def test_timeout_is_bounded_and_redacted():
    class S:
        def request(self,*a,**k): raise requests.Timeout('password=secret token=abc')
    try: WebODMClient(Config('http://fake','u','p'),session=S()).request('GET','/x')
    except WebODMError as e: assert 'secret' not in str(e) and 'abc' not in str(e) and '2 attempts' in str(e)
    else: assert False
    assert 'secret' not in redact('password=secret token=abc')

def test_malformed_response_is_explicit(tmp_path):
    class M(Fake):
        def task(self,p,t): return {"progress": 0.5}
    r=run(Config('http://fake','u','p',db_path=tmp_path/'j.sqlite'),images(tmp_path),tmp_path/'out',client=M([])); assert not r['ok'] and 'status' in r['error']['message']

def test_structured_exit_codes_for_missing_images():
    p=subprocess.run([sys.executable,'scripts/smoke_webodm.py'],capture_output=True,text=True); assert p.returncode==4; assert json.loads(p.stdout)['ok'] is False

def test_status_null_followed_by_running(tmp_path):
    f=Fake([{"status":None,"id":"t1"},{"status":20,"running_progress":.2},{"status":30,"last_error":"stop"}]); r=run(Config('http://fake','u','p',poll_interval=0,db_path=tmp_path/'j.sqlite'),images(tmp_path),tmp_path/'out',client=f); assert r['events'][0]['status']=='unknown'; assert r['events'][1]['status']=='running'

def test_missing_status_followed_by_completed(tmp_path):
    f=Fake([{"id":"t1"},{"status":40,"running_progress":1}]); r=run(Config('http://fake','u','p',poll_interval=0,db_path=tmp_path/'j.sqlite'),images(tmp_path),tmp_path/'out',client=f); assert r['ok']; assert r['events'][0]['status']=='unknown'

def test_unknown_status_bounded_timeout(tmp_path):
    f=Fake([{"status":None}]*3); c=Config('http://fake','u','p',poll_interval=0,db_path=tmp_path/'j.sqlite',max_unknown_polls=3); r=run(c,images(tmp_path),tmp_path/'out',client=f); assert not r['ok'] and 'retry policy exhausted' in r['error']['message']

def test_unknown_status_does_not_resubmit(tmp_path):
    f=Fake([{"status":None},{"status":40}]); c=Config('http://fake','u','p',poll_interval=0,db_path=tmp_path/'j.sqlite'); r=run(c,images(tmp_path),tmp_path/'out',client=f); assert r['ok']; assert f.submits==1

def test_event_history_persisted(tmp_path):
    f=Fake([{"status":None},{"status":40}]); c=Config('http://fake','u','p',poll_interval=0,db_path=tmp_path/'j.sqlite'); r=run(c,images(tmp_path),tmp_path/'out',client=f); row=JobStore(c.db_path).get(r['local_job_id']); assert 'unknown' in row['event_history']

def test_preflight_too_few_images(tmp_path):
    (tmp_path/'a.jpg').write_bytes(b'a');
    from astrakriti3d.storage import manifest_for_images
    try: manifest_for_images(tmp_path)
    except ValueError as e: assert 'At least two' in str(e)
    else: assert False

def test_legacy_manifest_reconciles_after_preflight_schema_change(tmp_path):
    p=tmp_path/'a.jpg'; q=tmp_path/'b.jpg'; p.write_bytes(b'a'); q.write_bytes(b'b'); m=manifest_for_images(tmp_path); st=JobStore(tmp_path/'j.sqlite'); legacy=[{k:v for k,v in x.items() if k in {'name','path','sha256','bytes'}} for x in m]; st.create('legacy','old-fingerprint',legacy,[]); assert st.find_by_manifest(m,[])['local_id']=='legacy'

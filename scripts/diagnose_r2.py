"""Read-only R2 investigation; --retry submits exactly one fresh, guarded task."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psutil
from astrakriti3d.client import WebODMClient
from astrakriti3d.config import Config
from astrakriti3d.selection_preflight import validate_selection, classify_failure
from astrakriti3d.storage import manifest_for_images

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/phase6/diagnosis-followup'
APPS = Path('C:/WebODM/resources/app/apps')
TASK = '9bc567e2-16e0-4f02-a840-a4a91db0e4ae'
IMAGES = ROOT / 'evidence/phase6/r2-selection/frames'
GEO = ROOT / 'evidence/phase6/experiment-corrected/R2/geo.txt'
SELECTION = ROOT / 'evidence/phase6/r2-selection/selection_manifest.json'


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(p, data):
    def clean(value):
        if isinstance(value, dict):
            return {k: ('[redacted]' if k.lower() in {'token', 'password', 'access_token'} else clean(v)) for k,v in value.items()}
        if isinstance(value, list): return [clean(v) for v in value]
        return value
    p.write_text(json.dumps(clean(data), indent=2), encoding='utf-8')


def resources():
    processes = []
    for p in psutil.process_iter(['pid', 'name', 'memory_info', 'num_threads', 'cpu_times']):
        try:
            if any(s in (p.info['name'] or '').lower() for s in ('python', 'node', 'webodm', 'opensfm')):
                d = p.info.copy()
                d['memory_info'] = d['memory_info']._asdict()
                d['cpu_times'] = d['cpu_times']._asdict()
                processes.append(d)
        except (psutil.Error, AttributeError):
            pass
    return {'utc': datetime.now(timezone.utc).isoformat(),
            'memory': psutil.virtual_memory()._asdict(), 'swap': psutil.swap_memory()._asdict(),
            'disk': psutil.disk_usage(str(ROOT))._asdict(), 'cpu_count': psutil.cpu_count(),
            'cpu_percent': psutil.cpu_percent(), 'processes': processes}


def hold_awake():
    """Temporary Windows idle-sleep inhibition, released on monitor completion."""
    import ctypes
    p=OUT/'exact-R2-retry/run.json'
    initial=p.stat().st_mtime_ns
    state=ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    if not state: raise OSError('Cannot acquire temporary idle-sleep lock')
    save(OUT/'exact-R2-retry/awake-lock.json',{'acquired_utc':datetime.now(timezone.utc).isoformat(),
         'scope':'this helper thread; idle system sleep only; no power-plan changes'})
    try:
        while p.stat().st_mtime_ns==initial:
            time.sleep(10)
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        save(OUT/'exact-R2-retry/awake-lock-released.json',{'released_utc':datetime.now(timezone.utc).isoformat()})


def normalize_log(raw):
    try:
        value = json.loads(raw)
        if isinstance(value, str): return value
        if isinstance(value, list): return '\n'.join(str(x) for x in value)
    except ValueError:
        pass
    return raw


def command(args, destination):
    r = subprocess.run(args, capture_output=True, text=True, timeout=300)
    data = {'command': args, 'exit_code': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}
    save(destination, data)
    return data


def investigate(c):
    OUT.mkdir(parents=True, exist_ok=True)
    save(OUT/'resources-before.json', resources())
    task = c.task('2', TASK)
    save(OUT/'original-task.json', task)
    log = normalize_log(c.output('2', TASK))
    (OUT/'original-engine.log').write_text(log, encoding='utf-8')
    save(OUT/'failure.json', classify_failure(OUT/'original-engine.log', task))
    preflight = validate_selection(IMAGES, GEO, SELECTION)
    save(OUT/'preflight.json', preflight)
    selection = json.loads(SELECTION.read_text())
    frames = selection['diagnostics']
    source = json.loads((ROOT/'evidence/phase4/real-run/prepared_manifest.json').read_text())
    save(OUT/'source-manifest-structure.json', {'keys': list(source), 'first_frame': source.get('frames', [])[:1]})
    comparison = []
    for i, frame in enumerate(frames):
        if frame['decision'] == 'reject':
            comparison.append({'removed': frame,
                               'previous_retained': next((x for x in reversed(frames[:i]) if x['decision']=='keep'), None),
                               'next_retained': next((x for x in frames[i+1:] if x['decision']=='keep'), None)})
    save(OUT/'selection-identities-reasons.json', selection)
    save(OUT/'removed-neighbors.json', comparison)
    records = []
    for p in (ROOT/'evidence/phase6').glob('experiment*/R*/experiment_result.json'):
        d = json.loads(p.read_text())
        records.append({'path': str(p), 'sha256': sha(p), 'ok': d.get('ok'),
                        'task_id': d.get('task_id'), 'image_count': len(d.get('preflight', {}).get('images', [])),
                        'keys': list(d), 'artifact_count': len(d.get('artifacts', []))})
    save(OUT/'experiment-provenance.json', records)
    for endpoint, name in (('/processingnodes/', 'processing-nodes.json'), ('/version/', 'api-version.json')):
        try: save(OUT/name, c.request('GET', endpoint).json())
        except Exception as e: save(OUT/name, {'unavailable': str(e)})
    versions = {'odx': (APPS/'ODX/VERSION').read_text().strip(),
                'nodeodx': json.loads((APPS/'NodeODX/package.json').read_text())['version'],
                'desktop_package': json.loads((APPS.parent/'package.json').read_text())['version']}
    save(OUT/'versions.json', versions)
    engine_python = str(APPS/'ODX/venv/Scripts/python.exe')
    command([engine_python, '-c', 'import cv2,sys; print(sys.version); print(cv2.__file__); print(cv2.__version__); print(cv2.getNumThreads()); print(cv2.getBuildInformation())'], OUT/'engine-opencv.json')
    code = """import cv2,hashlib,json,pathlib
items=[]
for p in sorted(pathlib.Path(%r).glob('*.jpg')):
    im=cv2.imread(str(p),cv2.IMREAD_UNCHANGED)
    if im is None: raise RuntimeError('decode failed: '+p.name)
    items.append({'name':p.name,'shape':list(im.shape),'dtype':str(im.dtype),'pixel_sha256':hashlib.sha256(im.tobytes()).hexdigest()})
print(json.dumps(items))
""" % str(IMAGES)
    command([engine_python, '-c', code], OUT/'engine-decode.json')
    # Failed NodeODX working directories can be cleaned by the service.
    ids = set(re.findall(r'NodeODX[\\/]data[\\/]([0-9a-f-]{36})', log))
    partial = []
    for ident in ids:
        directory = APPS/'NodeODX/data'/ident
        entry = {'path': str(directory), 'exists': directory.exists()}
        if directory.exists():
            entry['files'] = [{'path': str(p.relative_to(directory)), 'bytes': p.stat().st_size}
                              for p in directory.rglob('*') if p.is_file()]
        partial.append(entry)
    save(OUT/'partial-output-inventory.json', partial)
    print(json.dumps({'preflight_valid': preflight['valid'], 'count': preflight['image_count'],
                      'classification': classify_failure(OUT/'original-engine.log')['classification']}))
    return 0 if preflight['valid'] else 3


def retry(c):
    # mkdir is the durable one-attempt guard; never delete it to retry again.
    dest = OUT/'exact-R2-retry'
    dest.mkdir()
    started = time.monotonic()
    result = {'arm': 'R2-exact-retry', 'ok': False, 'terminal_status': None, 'artifacts': [],
              'command': sys.argv, 'original_task': TASK, 'started_utc': datetime.now(timezone.utc).isoformat()}
    task_id = None
    try:
        original = c.task('2', TASK)
        if original['status'] != 30: raise ValueError('original task is no longer failed')
        if original['options'] != []: raise ValueError('original options changed')
        shutil.copy2(GEO, dest/'geo.txt')
        preflight = validate_selection(IMAGES, dest/'geo.txt', SELECTION)
        save(dest/'preflight.json', preflight)
        if not preflight['valid'] or preflight['image_count'] != 185: raise ValueError('exact R2 preflight failed')
        shutil.copy2(SELECTION, dest/'selection_manifest.json')
        result.update({'image_count':185, 'geo_sha256':sha(dest/'geo.txt'), 'options':original['options'],
                       'versions':json.loads((OUT/'versions.json').read_text())})
        manifest = manifest_for_images(IMAGES)
        save(dest/'submitted-images.json', manifest)
        # Submit directly once: the normal runner deliberately reuses failed fingerprints.
        submitted = time.monotonic()
        task_id = c.submit_task('2', manifest, original['options'], geo_txt=dest/'geo.txt')
        result['task_id'] = task_id
        result['upload_seconds'] = time.monotonic() - submitted
        save(dest/'run.json', result)
        with (dest/'resources.jsonl').open('a', encoding='utf-8') as samples:
            while True:
                samples.write(json.dumps(resources())+'\n'); samples.flush()
                task = c.task('2', task_id)
                save(dest/'task.json', task)
                with (dest/'events.jsonl').open('a', encoding='utf-8') as f:
                    f.write(json.dumps({'elapsed_seconds':time.monotonic()-started, 'status':task.get('status'),
                                        'progress':task.get('running_progress')})+'\n')
                (dest/'engine.log').write_text(normalize_log(c.output('2', task_id)), encoding='utf-8')
                if task.get('status') in (30,40,50): break
                if time.monotonic()-started > 7200: raise TimeoutError('monitor deadline; task may still be running')
                time.sleep(15)
        result['terminal_status'] = task['status']
        result['processing_time_ms'] = task.get('processing_time')
        result['effective_options'] = task.get('options')
        if task['status'] == 40:
            for asset in ('orthophoto.tif','shots.geojson','cameras.json','report.pdf','georeferenced_model.laz','textured_model.zip','textured_model.glb'):
                if asset in task.get('available_assets', []):
                    p = dest/'artifacts'/asset
                    c.download('2', task_id, asset, p)
                    result['artifacts'].append({'name':asset, 'bytes':p.stat().st_size, 'sha256':sha(p)})
            required = {'orthophoto.tif','shots.geojson','cameras.json','report.pdf','georeferenced_model.laz'}
            result['ok'] = required <= {x['name'] for x in result['artifacts']}
        else:
            result['failure'] = classify_failure(dest/'engine.log', task)
    except Exception as e:
        result['error'] = {'type':type(e).__name__, 'message':str(e)}
    finally:
        result['inclusive_seconds'] = time.monotonic()-started
        result['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save(dest/'run.json', result)
    print(json.dumps(result))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    p = argparse.ArgumentParser(); group=p.add_mutually_exclusive_group(); group.add_argument('--retry', action='store_true'); group.add_argument('--hold-awake', action='store_true'); a=p.parse_args()
    if a.hold_awake:
        hold_awake(); sys.exit(0)
    client = WebODMClient(Config.from_env()); client.authenticate()
    sys.exit(retry(client) if a.retry else investigate(client))

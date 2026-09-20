import json
from pathlib import Path
from astrakriti3d import web
from astrakriti3d.storage import JobStore

def test_summary_endpoint_is_read_only_and_labels_r1():
    client=web.create_app().test_client(); r=client.get('/api/summary')
    assert r.status_code==200
    d=r.get_json(); assert d['read_only'] is True
    assert d['project']['production_baseline']=='R1'
    assert d['reconstruction']['experimental']['R2'].startswith('unpromoted')
    assert d['validation']['accuracy']=='unverified'
    assert all('sha256' in a for a in d['artifacts'])

def test_health_does_not_expose_credentials():
    d=web.create_app().test_client().get('/api/health').get_json()
    assert d['webodm_credentials_exposed'] is False

def test_retired_dashboard_redirects_to_configured_webodm_and_disables_static_ui(monkeypatch):
    monkeypatch.setenv('WEBODM_BASE_URL', 'https://webodm.example/odm/')
    client = web.create_app().test_client()

    response = client.get('/', follow_redirects=False)
    assert response.status_code == 302
    assert response.headers['Location'] == 'https://webodm.example/odm/astrakriti/overview/'
    assert client.get('/index.html').status_code == 404
    assert client.get('/app.js').status_code == 404
    assert client.get('/api/health').status_code == 200

def test_retired_dashboard_reports_missing_webodm_configuration(monkeypatch):
    monkeypatch.setenv('WEBODM_BASE_URL', '')
    response = web.create_app().test_client().get('/')
    assert response.status_code == 410
    assert response.get_json()['error'] == 'standalone_dashboard_retired'
    assert 'WEBODM_BASE_URL' in response.get_json()['detail']

def test_retired_dashboard_rejects_credential_bearing_redirect_url(monkeypatch):
    monkeypatch.setenv('WEBODM_BASE_URL', 'https://operator:secret@webodm.example')
    response = web.create_app().test_client().get('/')
    assert response.status_code == 410
    assert 'secret' not in response.get_data(as_text=True)

def test_missing_and_malformed_evidence_are_safe(monkeypatch, tmp_path):
    original=web.ROOT; monkeypatch.setattr(web,'ROOT',tmp_path)
    try:
        d=web.build_summary(); assert d['frames']['count']==0; assert d['telemetry']['status']=='incomplete'
    finally: monkeypatch.setattr(web,'ROOT',original)

def test_dashboard_ignores_screenshot_fixture(monkeypatch, tmp_path):
    fixture_dir = tmp_path / 'config'; fixture_dir.mkdir()
    (fixture_dir / 'dashboard_overview.json').write_text(json.dumps({
        'summary': {'active': 1, 'completed': 12, 'failed': 2},
        'active_run': {'id': 'R2', 'mission': 'SITE ALPHA', 'progress': 42},
    }), encoding='utf-8')
    original=web.ROOT; monkeypatch.setattr(web,'ROOT',tmp_path)
    try:
        dashboard = web.build_summary()['dashboard']
        assert dashboard['state'] == 'first_use'
        assert dashboard['summary'] == {'active': 0, 'completed': 0, 'failed': 0}
        assert 'SITE ALPHA' not in json.dumps(dashboard)
    finally: monkeypatch.setattr(web,'ROOT',original)

def test_dashboard_first_use_comes_from_empty_job_store(monkeypatch, tmp_path):
    original=web.ROOT; monkeypatch.setattr(web,'ROOT',tmp_path)
    try:
        dashboard = web.build_summary()['dashboard']
        assert dashboard['state'] == 'first_use'
        assert dashboard['summary'] == {'active': 0, 'completed': 0, 'failed': 0}
        assert dashboard['active_run'] is None
        assert dashboard['latest_run'] is None
        assert dashboard['entity_counts'] == {'missions': 0, 'runs': 0, 'artifacts': 0}
        assert dashboard['recent_reconstructions'] == []
        assert dashboard['artifacts'] == []
        assert dashboard['notices'] == []
        assert dashboard['first_use_state']['title'] == 'NO RECONSTRUCTIONS YET'
        assert dashboard['first_use_state']['body'] == 'Create your first reconstruction workspace.'
        assert len(dashboard['first_use_state']['setup_steps']) == 5
        assert dashboard['empty_sections'] == {
            'recent': 'No Runs have been created yet.',
            'artifacts': 'Artifacts will appear here after the first successful Run.',
            'notices': 'No active notices.',
        }
    finally: monkeypatch.setattr(web,'ROOT',original)

def test_dashboard_idle_with_history_uses_latest_real_run(monkeypatch, tmp_path):
    images = tmp_path / 'mission-input'; images.mkdir()
    manifest = []
    for index in range(2):
        path = images / f'frame_{index:06d}.jpg'; path.write_bytes(b'frame')
        manifest.append({'name': path.name, 'path': str(path), 'sha256': f'frame-{index}'})
    store = JobStore(tmp_path / 'runtime' / 'jobs.sqlite3')
    store.create('complete-run', 'complete-fingerprint', manifest, [])
    store.update('complete-run', project_id='7', task_id='task-7', state='completed', progress=1.0)
    store.create('failed-run', 'failed-fingerprint', manifest, [])
    store.update('failed-run', project_id='7', task_id='task-8', state='failed', diagnostics={'error': 'actual failure'})
    original=web.ROOT; monkeypatch.setattr(web,'ROOT',tmp_path); monkeypatch.setattr(web, '_project_job', lambda row: True)
    try:
        dashboard = web.build_summary()['dashboard']
        assert dashboard['state'] == 'no_active'
        assert dashboard['summary'] == {'active': 0, 'completed': 1, 'failed': 1}
        assert dashboard['entity_counts']['runs'] == 2
        assert dashboard['latest_run']['id'] == 'failed-run'
        assert dashboard['latest_run']['status'] == 'failed'
        assert dashboard['latest_run']['available_outputs'] == []
        assert dashboard['empty_state']['body'] == 'No reconstruction is currently processing.'
        assert dashboard['empty_state']['detail'] == 'Start a new reconstruction when you are ready.'
    finally: monkeypatch.setattr(web,'ROOT',original)

def test_dashboard_maps_persisted_job_states_and_artifacts(monkeypatch, tmp_path):
    images = tmp_path / 'mission-input'; images.mkdir()
    manifest = []
    for index in range(2):
        path = images / f'frame_{index:06d}.jpg'; path.write_bytes(b'frame')
        manifest.append({'name': path.name, 'path': str(path), 'sha256': 'frame-hash'})
    store = JobStore(tmp_path / 'runtime' / 'jobs.sqlite3')
    store.create('processing-run', 'processing-fingerprint', manifest, [])
    store.update('processing-run', project_id='7', task_id='task-7', state='running', progress=0.4284)
    store.create('failed-run', 'failed-fingerprint', manifest, [])
    store.update('failed-run', project_id='7', task_id='task-8', state='failed', progress=0.85, diagnostics={'error': 'actual failure'})
    artifact = tmp_path / 'outputs' / 'orthophoto.jpg'; artifact.parent.mkdir(); artifact.write_bytes(b'output')
    store.create('complete-run', 'complete-fingerprint', manifest, [])
    store.update('complete-run', project_id='7', task_id='task-9', state='completed', progress=1.0, artifacts=[{'name': artifact.name, 'path': str(artifact)}])
    original=web.ROOT; monkeypatch.setattr(web,'ROOT',tmp_path); monkeypatch.setattr(web, '_project_job', lambda row: True)
    try:
        dashboard = web.build_summary()['dashboard']
        assert dashboard['state'] == 'active_processing'
        assert dashboard['summary'] == {'active': 1, 'completed': 1, 'failed': 1}
        assert dashboard['active_run']['id'] == 'processing-run'
        assert dashboard['active_run']['progress'] == 42.84
        assert dashboard['active_run']['frame_count'] == 2
        assert dashboard['artifacts'][0]['exists'] is True
        assert any(item['title'] == 'Run failed-run failed' for item in dashboard['notices'])
        media_response = web.create_app().test_client().get('/api/dashboard/media/complete-run/orthophoto')
        assert media_response.status_code == 200
    finally: monkeypatch.setattr(web,'ROOT',original)

def test_dashboard_database_failure_returns_clear_error(monkeypatch, tmp_path):
    db_path = tmp_path / 'runtime' / 'jobs.sqlite3'; db_path.parent.mkdir()
    db_path.write_bytes(b'not a sqlite database')
    original=web.ROOT; monkeypatch.setattr(web,'ROOT',tmp_path)
    try:
        response = web.create_app().test_client().get('/api/summary')
        assert response.status_code == 503
        assert 'database' in response.get_json()['error'].lower()
    finally: monkeypatch.setattr(web,'ROOT',original)

def test_dashboard_exposes_credential_free_webodm_viewer_link(monkeypatch, tmp_path):
    images = tmp_path / 'mission-input'; images.mkdir()
    frame = images / 'frame_000001.jpg'; frame.write_bytes(b'frame')
    store = JobStore(tmp_path / 'runtime' / 'jobs.sqlite3')
    store.create('viewer-run', 'viewer-fingerprint', [{'name': frame.name, 'path': str(frame), 'sha256': 'frame-hash'}], [])
    store.update('viewer-run', project_id='project/7', task_id='task/9', state='completed', progress=1.0)
    original = web.ROOT
    monkeypatch.setattr(web, 'ROOT', tmp_path)
    monkeypatch.setattr(web, '_project_job', lambda row: True)
    monkeypatch.setenv('WEBODM_BASE_URL', 'http://webodm.local')
    try:
        row = web.build_summary()['dashboard']['recent_reconstructions'][0]
        assert row['webodm_viewer_url'] == 'http://webodm.local/map/project/project%2F7/task/task%2F9/'
        assert 'password' not in row['webodm_viewer_url']
    finally:
        monkeypatch.setattr(web, 'ROOT', original)

def test_frontend_has_empty_loading_and_future_navigation_labels():
    html=Path('web/index.html').read_text(encoding='utf-8')
    assert 'Loading' in html and 'Coming later' in html and 'Frame review' in html
    assert 'empty-state-setup' in html and 'empty-state-technical' in html
    assert 'latest-activity' in html and 'idle-state-technical' in html
    assert 'No Runs have been created yet.' in html

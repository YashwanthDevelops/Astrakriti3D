import json
from pathlib import Path
from astrakriti3d import web

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

def test_missing_and_malformed_evidence_are_safe(monkeypatch, tmp_path):
    original=web.ROOT; monkeypatch.setattr(web,'ROOT',tmp_path)
    try:
        d=web.build_summary(); assert d['frames']['count']==0; assert d['telemetry']['status']=='incomplete'
    finally: monkeypatch.setattr(web,'ROOT',original)

def test_frontend_has_empty_loading_and_future_navigation_labels():
    html=Path('web/index.html').read_text(encoding='utf-8')
    assert 'Loading' in html and 'Coming later' in html and 'Frame review' in html

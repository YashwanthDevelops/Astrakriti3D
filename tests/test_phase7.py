import json
from pathlib import Path
from astrakriti3d.phase7 import validate_baseline, stats, coordinate_errors, transform, Phase7ValidationError, evaluate

def test_phase7_stats_and_coordinate_metrics():
    assert stats([1, 2, 3]) == {'sample_count': 3, 'median': 2.0, 'rmse': (14/3)**0.5, 'p95': 2.9, 'maximum': 3.0}
    e = coordinate_errors((500000, 0, 12), (500000, 0, 10), 'EPSG:32637', 'EPSG:32637', reference_uncertainty=.25)
    assert e['horizontal'] == 0 and e['vertical'] == 2 and e['three_dimensional'] == 2 and e['reference_uncertainty'] == .25
    assert transform((39, 0, 0), 'EPSG:4326', 'EPSG:32637')[0] == 500000

def test_phase7_rejects_bad_crs_and_unknown_unit():
    import pytest
    with pytest.raises(Phase7ValidationError): transform((0, 0), 'EPSG:9999', 'EPSG:32637')
    with pytest.raises(Phase7ValidationError): coordinate_errors((0,0), (0,0), 'EPSG:32637', 'EPSG:32637', 'yards')

def test_phase7_unverified_evaluation_is_deterministic(tmp_path):
    a=tmp_path/'artifacts'; a.mkdir(); (a/'model.laz').write_bytes(b'laz')
    r1=evaluate(artifact_dir=a, output=tmp_path/'one')
    r2=evaluate(artifact_dir=a, output=tmp_path/'two')
    assert r1 == r2 and r1['accuracy']['status']=='unverified' and r1['completeness']['status']=='audit_template'


def test_phase7_reports_internal_consistency_and_unverified_accuracy(tmp_path):
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"artifact")
    import hashlib
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"artifacts": [{"name": "artifact.bin", "path": str(artifact), "sha256": hashlib.sha256(b"artifact").hexdigest()}]}))
    association = tmp_path / "association.json"
    association.write_text(json.dumps({"rows": [{"frame_filename": "frame_000001.jpg", "association_status": "matched", "latitude": 0.364, "longitude": 36.872, "frame_timestamp_seconds": 0.0}]}))
    shots = tmp_path / "shots.json"
    shots.write_text(json.dumps({"features": [{"properties": {"filename": "frame_000001.jpg"}, "geometry": {"coordinates": [36.872, 0.364, 1]}}]}))
    report = validate_baseline(inventory=inventory, association=association, shots=shots, output=tmp_path / "out")
    assert report["offline_only"] and report["webodm_submitted"] is False
    assert report["internal_geolocation_consistency"]["matched_camera_count"] == 1
    assert report["accuracy"]["status"] == "unverified"
    assert (tmp_path / "out" / "phase7_validation.json").is_file()

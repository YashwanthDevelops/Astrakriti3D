import json
from pathlib import Path
from astrakriti3d.telemetry import parse_srt, associate, inspect_metadata

def srt(*blocks): return "\n\n".join(blocks) + "\n"
def block(n, t, lat="1.0", lon="2.0", alt="4.0"):
    return f"{n}\n00:00:{t},000 --> 00:00:{t},100\n[latitude: {lat}] [longitude: {lon}] [altitude: {alt}]"

def test_parse_semantics_and_raw_provenance(tmp_path):
    p=tmp_path/'x.srt'; raw=srt(block(1,'01'),block(2,'02','-1.2','179.5')); p.write_text(raw)
    records, meta=parse_srt(p)
    assert len(records)==2 and records[1].latitude == -1.2
    assert records[0].raw_text.startswith('[latitude')
    assert meta['semantics']['coordinate_order']=='latitude, longitude'
    assert meta['semantics']['altitude_confidence']=='unknown'

def test_association_signed_tolerance_and_no_interpolation():
    p=Path('tests/_phase3.srt'); p.write_text(srt(block(1,'00'),block(2,'02')))
    records,_=parse_srt(p)
    rows,diffs=associate([{'output_filename':'a.jpg','source_timestamp_seconds':0.2},{'output_filename':'b.jpg','source_timestamp_seconds':1.0}],records,.3)
    assert rows[0]['association_status']=='matched' and rows[0]['signed_time_difference_seconds']==-.2
    assert rows[1]['association_status']=='unmatched'
    p.unlink()

def test_diagnostics_and_deterministic_report(tmp_path):
    s=tmp_path/'x.srt'; s.write_text(srt(block(1,'00'),block(2,'01')))
    m=tmp_path/'manifest.json'; m.write_text(json.dumps({'frames':[{'output_filename':'a.jpg','source_timestamp_seconds':0.0}]}))
    v=tmp_path/'v.mp4'; v.write_bytes(b'video')
    a=inspect_metadata(v,s,m,tmp_path/'a'); b=inspect_metadata(v,s,m,tmp_path/'b')
    assert a['association']==b['association'] and a['srt']['sha256']==b['srt']['sha256']

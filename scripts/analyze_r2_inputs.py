"""Offline input/continuity audit; does not run reconstruction or assess accuracy."""
import collections
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.diagnose_r2 import ROOT, OUT, save, sha
from astrakriti3d.selection_preflight import validate_selection


def main():
    import cv2
    from PIL import Image
    source_dir = ROOT/'evidence/phase4/real-run/images'
    source_manifest = json.loads((ROOT/'evidence/phase2/real-run/manifest.json').read_text())
    timestamps = {x['output_filename']: x['source_timestamp_seconds'] for x in source_manifest['frames']}
    selection = json.loads((OUT/'selection-identities-reasons.json').read_text())
    report = validate_selection(source_dir, ROOT/'evidence/phase4/real-run/geo.txt')
    save(OUT/'all-194-preflight.json', report)
    metadata = []
    for p in sorted(source_dir.glob('*.jpg')):
        with Image.open(p) as im:
            e = im.getexif()
            metadata.append({'name':p.name, 'format':im.format, 'mode':im.mode,
                             'exif_tags':sorted(e.keys()), 'make':str(e.get(271,'')), 'model':str(e.get(272,'')),
                             'focal_length':str(e.get(37386,'')), 'progressive':bool(im.info.get('progressive')),
                             'icc_profile_present':bool(im.info.get('icc_profile'))})
    save(OUT/'encoding-metadata.json',metadata)
    rows = selection['diagnostics']
    actual = {x['name']:x['sha256'] for x in report['images']}
    assert all(actual[x['output_filename']]==x['source_sha256'] for x in rows)
    orb = cv2.ORB_create(nfeatures=500)
    def descriptor(name):
        im=cv2.imread(str(source_dir/name),cv2.IMREAD_GRAYSCALE)
        if im is None: raise ValueError(name)
        return orb.detectAndCompute(cv2.resize(im,(320,180),interpolation=cv2.INTER_AREA),None)[1]
    bridges = []
    for i,x in enumerate(rows):
        if x['decision']!='reject': continue
        prev=next(d for d in reversed(rows[:i]) if d['decision']=='keep')
        nex=next(d for d in rows[i+1:] if d['decision']=='keep')
        a,b=prev['output_filename'],nex['output_filename']
        da,db=descriptor(a),descriptor(b)
        matches=cv2.BFMatcher(cv2.NORM_HAMMING,crossCheck=True).match(da,db) if da is not None and db is not None else []
        bridges.append({'removed':x['output_filename'], 'previous_retained':a,'next_retained':b,
                        'retained_gap_seconds':timestamps[b]-timestamps[a], 'bridge_orb_crosscheck_matches':len(matches),
                        'bridge_matches_distance_le_32':sum(m.distance<=32 for m in matches),
                        'removed_reasons':x['reason']})
    kept=[x['output_filename'] for x in rows if x['decision']=='keep']
    anchors=[x['output_filename'] for x in rows if any(r in x['reason'] for r in ('endpoint_protected','temporal_continuity_protected','viewpoint_change_or_uncertain'))]
    groups={}
    for decision in ('keep','reject'):
        values=[x['diagnostics']['blur_laplacian_variance'] for x in rows if x['decision']==decision]
        groups[decision]={'minimum_proxy_blur':min(values), 'maximum_proxy_blur':max(values),
                          'below_configured_blur_floor':sum(v<selection['configuration']['min_blur_laplacian_variance'] for v in values)}
    engine=json.loads((OUT/'engine-decode.json').read_text())
    decoded=json.loads(engine['stdout']) if engine['exit_code']==0 else []
    pixels=collections.defaultdict(list)
    for x in decoded: pixels[x['pixel_sha256']].append(x['name'])
    summary={'all_194_valid':report['valid'], 'source_hashes_match_all_decisions':True,
             'kept_count':len(kept), 'rejected_count':len(bridges), 'anchors':anchors,
             'all_declared_anchors_retained':set(anchors)<=set(kept),
             'maximum_retained_time_gap_seconds':max(timestamps[b]-timestamps[a] for a,b in zip(kept,kept[1:])),
             'bridges':bridges, 'blur':groups,'engine_decoded_count':len(decoded),
             'engine_pixel_duplicates':[v for v in pixels.values() if len(v)>1],
             'limitations':['ORB matches are proxy support, not proof of photogrammetric connectivity or scene coverage.',
                             'No independent coverage anchors or accuracy references are defined in this selector.']}
    save(OUT/'input-continuity-summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('anchors','bridges')}))
    return 0 if report['valid'] else 3


if __name__=='__main__': sys.exit(main())

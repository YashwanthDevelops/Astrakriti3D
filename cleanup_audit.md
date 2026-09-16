# Astrakriti3D cleanup audit

Read-only audit. No file was deleted, moved, renamed, or modified by the audit.

Inventory: 7,852 files, 268 directories, 27.934 GB.

## Category totals

| Category | Files | Directories | Size (GB) |
|---|---:|---:|---:|
| Required for production | 34 | 4 | 3.761 |
| Required for tests | 32 | 1 | 0.093 |
| Required for reproducibility/evidence | 628 | 141 | 1.333 |
| Experimental but should be retained | 78 | 17 | 0.109 |
| Generated artifact that can be archived | 7,043 | 97 | 22.523 |
| Temporary/cache file that is safe to delete | 34 | 6 | 0.000 |
| Duplicate or obsolete file | 0 | 0 | 0.000 |
| Unclear — requires human confirmation | 3 | 2 | 0.115 |

## Proposed archive list

No additional archive move is proposed; existing archive contents are retained.

- None

## Proposed deletion list

Only unreferenced cache files are proposed; no deletion was performed.

- `archive/housekeeping-20260915/caches/.pytest_cache/CACHEDIR.TAG` — 191 bytes; references: none
- `archive/housekeeping-20260915/caches/.pytest_cache/v/cache/lastfailed` — 2 bytes; references: none
- `archive/housekeeping-20260915/caches/.pytest_cache/v/cache/nodeids` — 6314 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/__init__.cpython-312.pyc` — 211 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/baseline.cpython-312.pyc` — 16037 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/client.cpython-312.pyc` — 9319 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/config.cpython-312.pyc` — 3657 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/coverage_selection.cpython-312.pyc` — 22413 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/geolocation.cpython-312.pyc` — 7954 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/phase7.cpython-312.pyc` — 17343 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/resources.cpython-312.pyc` — 3174 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/runner.cpython-312.pyc` — 10712 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/selection.cpython-312.pyc` — 19640 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/selection_preflight.cpython-312.pyc` — 11111 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/storage.cpython-312.pyc` — 10976 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/telemetry.cpython-312.pyc` — 17256 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/video.cpython-312.pyc` — 17732 bytes; references: none
- `archive/housekeeping-20260915/caches/astrakriti3d____pycache__/web.cpython-312.pyc` — 7520 bytes; references: none
- `archive/housekeeping-20260915/caches/scripts____pycache__/submit_coverage_aware_webodm.cpython-312.pyc` — 9585 bytes; references: none
- `archive/housekeeping-20260915/caches/scripts____pycache__/validate_r1_baseline.cpython-312.pyc` — 10782 bytes; references: none
- `archive/housekeeping-20260915/caches/tests____pycache__/test_adaptive_selection.cpython-312-pytest-9.1.1.pyc` — 8957 bytes; references: none
- `archive/housekeeping-20260915/caches/tests____pycache__/test_phase1.cpython-312-pytest-9.1.1.pyc` — 41902 bytes; references: none
- `archive/housekeeping-20260915/caches/tests____pycache__/test_phase2.cpython-312-pytest-9.1.1.pyc` — 47500 bytes; references: none
- `archive/housekeeping-20260915/caches/tests____pycache__/test_phase3.cpython-312-pytest-9.1.1.pyc` — 8954 bytes; references: none
- `archive/housekeeping-20260915/caches/tests____pycache__/test_phase4.cpython-312-pytest-9.1.1.pyc` — 19300 bytes; references: none
- `archive/housekeeping-20260915/caches/tests____pycache__/test_phase5.cpython-312-pytest-9.1.1.pyc` — 7416 bytes; references: none
- `archive/housekeeping-20260915/caches/tests____pycache__/test_phase6_offline.cpython-312-pytest-9.1.1.pyc` — 7853 bytes; references: none
- `archive/housekeeping-20260915/caches/tests____pycache__/test_phase7.cpython-312-pytest-9.1.1.pyc` — 11121 bytes; references: none
- `archive/housekeeping-20260915/caches/tests____pycache__/test_r1_baseline.cpython-312-pytest-9.1.1.pyc` — 2929 bytes; references: none
- `archive/housekeeping-20260915/caches/tests____pycache__/test_selection.cpython-312-pytest-9.1.1.pyc` — 6303 bytes; references: none
- `archive/housekeeping-20260915/caches/tests____pycache__/test_selection_preflight.cpython-312-pytest-9.1.1.pyc` — 26400 bytes; references: none
- `archive/housekeeping-20260915/caches/tests____pycache__/test_web.cpython-312-pytest-9.1.1.pyc` — 8439 bytes; references: none

## Reference and safety notes

- Python imports, CLI entry points, tests, package metadata, documentation, configuration, and evidence references were scanned.
- Evidence and experimental selector material is retained conservatively, even when old or unsuccessful.
- `.env` is classified as unclear because it contains local credentials/configuration.
- 7041 archived records have literal basename/path matches in historical text; these are ambiguous evidence links, not deletion candidates.
- Complete per-file and per-directory classifications are in `cleanup_audit.json`.

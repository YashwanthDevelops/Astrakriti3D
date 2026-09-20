# Phase 0–5 reconciliation

Recorded 2026-09-16. This is an evidence report. The implementation plan
remains unchanged.

## Current integration overlay — 2026-09-18

The Phase 0–5 entries below are historical evidence from the earlier
adapter-based runtime and must not be reused as the current WebODM product
acceptance gate. The current production boundary is the maintained WebODM
`coreplugins/astrakriti3d` plugin plus the preparation-only companion. The
current Astrakriti suite has 145 passing tests, but Docker Desktop currently
fails during Ingest initialization because it cannot access the
`sailor-ingest.sock` reparse entries; the WebODM Django/browser gate is
therefore still blocked. Legacy Mission/Run/Job reconciliation is now handled
additively by WebODM's `AstrakritiLegacyLink` model and the preview-first
`astrakriti_reconcile` command. No historical PASS below supersedes this
current-state limitation.

| Phase | Requirement | Implementation/evidence | Status | Relevant file/test/command | Explanation |
|---|---|---|---|---|---|
| 0 | Branch identified | `main` at `66bd1df` | PASS | `git branch --show-current` | Verified. |
| 0 | Working tree and baseline protected | Baseline commit and complete known-change inventory recorded; no runs/evidence deleted | PASS | `git rev-parse HEAD`, `git status --short`, `docs/PHASE_0_BASELINE.md` | The plan’s clean-tree condition is represented honestly: accepted implementation/evidence changes remain uncommitted and protected. |
| 0 | Python version | 3.12.0 | PASS | `python --version` | Verified. |
| 0 | FFmpeg version | 9.0.1 full build | PASS | `ffmpeg -version` | Verified. |
| 0 | Docker version/engine | Docker Server 29.8.0, Linux engine operational | PASS | `docker info`, `docker context show`, `docker run --rm hello-world` | Context `desktop-linux`; server responded successfully. |
| 0 | NodeODM/WebODM versions | WebODM 3.3.0 and official NodeODM image recorded | PASS | WebODM commit `2e26f5321e6bcccab91662c024d2c0a9bbea2d9d`; compose status/logs | Untouched upstream checkout and `webodm/nodeodx:latest` runtime evidence recorded. |
| 0 | Tests recorded | 135 passed | PASS | `python -m pytest -q` | 0 failed, skipped, or errors. |
| 0 | CLI/dashboard entry points | `run_astrakriti.py`, `run_web.py` | PASS | Repository inspection | Verified. |
| 0 | Exit gate | Existing test suite and protected baseline documented; environment/runtime facts now complete | ACCEPTED | `docs/PHASE_0_BASELINE.md` | Phase 0 is closed. |
| 1 | Background WebODM API | Client and orchestration code exist and runtime is accepted | ACCEPTED | `astrakriti3d/client.py`, live WebODM fixture evidence | Phase 1 was accepted before this closure. |
| 1 | Authentication/project/task/upload | Real runtime authenticated and accepted a fixture | ACCEPTED | WebODM UI/runtime evidence | Phase 1 was accepted before this closure. |
| 1 | Polling/cancellation/errors/downloads | Real task completed and outputs were exposed | ACCEPTED | WebODM task/output evidence | Phase 1 was accepted before this closure. |
| 1 | Restart reconciliation | Persisted task reuse implemented and tested | ACCEPTED | `astrakriti3d/runner.py`, tests | Phase 1 was accepted before this closure. |
| 1 | Untouched fixture completes | Official untouched fixture completed successfully | ACCEPTED | Recorded task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6` | Phase 1 was accepted before this closure. |
| 2 | Separate upstream/product sources | Separate `integrations/` boundary | ACCEPTED | `docs/INTEGRATION_BOUNDARY.md` | Phase 2 was accepted before this closure. |
| 2 | Adapter boundary contract | Adapter implements project/task/status/cancel/assets/health | ACCEPTED | `integrations/webodm_adapter.py`, tests | Phase 2 was accepted before this closure. |
| 2 | Application configuration | Name, theme and upstream checkout configured | ACCEPTED | `config/astrakriti3d.json` | Phase 2 was accepted before this closure. |
| 2 | WebODM/NodeODM health | Non-mutating adapter health check verifies an online processing node | PASS | `WebODMAdapter.health_check`; live check returned `True` against WebODM 3.3.0 / NodeODM |
| 2 | Upstream attribution | Boundary and license notes present | ACCEPTED | `docs/INTEGRATION_BOUNDARY.md`, `LICENSE_NOTES.md` | Phase 2 was accepted before this closure. |
| 2 | All adapter operations real-tested | Live adapter authenticated, created/looked up project, submitted task, read status, cancelled via contract, retrieved asset, and checked health | PASS | `integrations/webodm_adapter.py`; live task `bc217fa8-a5c7-48ff-ad4a-aa7fa969fe58`; focused adapter tests |
| 2 | No direct WebODM bypass | Runner uses `WebODMAdapter` for project/task/status/cancel/assets; transport remains an implementation detail | PASS | `astrakriti3d/runner.py`, `integrations/webodm_adapter.py` |
| 2 | Exit gate | Astrakriti3D operations are exposed through the adapter boundary and live WebODM verification passed | ACCEPTED | Live WebODM check and adapter-backed submission |
| 3 | Mission/Run/artifact/evidence persistence | SQLite ProductStore | PASS | `astrakriti3d/domain.py`, `tests/test_domain.py` | Persisted and reload-tested. |
| 3 | Normal lifecycle | Explicit transition table | PASS | `astrakriti3d/domain.py`, `tests/test_domain.py` | Full normal path tested. |
| 3 | Failure/cancel/partial/recovery | States and transitions retained | PASS | `astrakriti3d/domain.py`, `tests/test_domain.py`, `tests/test_recovery.py` | Existing behavior preserved. |
| 3 | Invalid/repeated transitions | Validation plus same-state idempotency | PASS | `tests/test_domain.py` | Verified. |
| 3 | Task identity/conflicts | Conditional task recording and conflict rejection | PASS | `astrakriti3d/storage.py`, `tests/test_orchestration_submission.py` | Verified at persistence boundary. |
| 3 | Duplicate logical submissions | Atomic reservation plus persisted fingerprint/task reuse | PASS | `astrakriti3d/storage.py`, `astrakriti3d/runner.py`, `tests/test_orchestration_submission.py` | First submission is one call; reload reuses it. |
| 3 | Failed submissions retry | Failed runner state remains retryable | PASS | `tests/test_orchestration_submission.py` | Verified with fake adapter. |
| 3 | Real runner consumes guard | Adapter-backed `runner.run` reserves persisted identity before submission and records/reuses the WebODM task identity | PASS | `astrakriti3d/runner.py`, `astrakriti3d/storage.py`, `tests/test_orchestration_submission.py` |
| 3 | Exit gate | Run submission is restart-safe, idempotent, conflict-protected, and retryable | ACCEPTED | Focused + full tests; live adapter-backed runner submission |
| 4 | Video ingestion and metadata | Separate one-minute DJI fixture inspected without modifying the original | ACCEPTED | `scripts/create_phase4_fixture.py`; fixture `60.026633s`, source `193.593400s` |
| 4 | Deterministic extraction and manifests | Local and georeferenced routes produced reproducible 30-frame manifests and SHA-256 hashes | ACCEPTED | `astrakriti3d/video.py`, `astrakriti3d/project.py`, real evidence directories |
| 4 | SRT parsing and frame association | 1,799 valid records; 30/30 frames matched; zero parser errors; maximum difference `0.003633s` | ACCEPTED | `astrakriti3d/telemetry.py`, `telemetry_report.json` |
| 4 | Local/georeferenced inputs | Local output omitted geographic inputs; georeferenced output generated EPSG:4326 `geo.txt` and prepared images | ACCEPTED | `project_report.json`, `geo.txt`, `prepared_manifest.json` |
| 4 | Preflight and asynchronous preparation | Dedicated preflight passed; persistent queue completed the real georeferenced fixture | ACCEPTED | `evidence/phase4/preflight-georeferenced`, `queue-state.json`, `PreparationQueue` |
| 4 | Exit gate | Video-only and video-plus-SRT workflows produced valid reproducible task inputs and complete manifests | ACCEPTED | Focused Phase 4 tests and real fixture evidence |

## Final phase decisions

- Phase 0: **ACCEPTED/CLOSED** — baseline, protection, versions, runtime, and tests are documented.
- Phase 1: **ACCEPTED** — untouched WebODM fixture completed successfully.
- Phase 2: **ACCEPTED** — adapter boundary, configuration, attribution, health, and all required operations are implemented; live adapter verification passed.
- Phase 3: **ACCEPTED** — lifecycle persistence, restart reuse, conflict handling, retry behavior, and the actual adapter-backed runner submission guard pass.
- Phase 4: **ACCEPTED** — real one-minute video/SRT ingestion, deterministic preparation, telemetry association, preflight, and asynchronous queue evidence pass.

## Phase 0 closure

Phase 0 is **ACCEPTED/CLOSED**. The baseline branch is `main` at protected
commit `66bd1df`; the known implementation/evidence changes are listed by
`git status --short` and preserved. Python 3.12.0, FFmpeg 9.0.1, Docker Server
29.8.0 on `desktop-linux`, WebODM 3.3.0 at upstream commit
`2e26f5321e6bcccab91662c024d2c0a9bbea2d9d`, NodeODM, the accepted real fixture,
and the full suite result of `134 passed` are recorded. Astrakriti3D source,
runs, evidence, and configuration were preserved.

Phase 1, Phase 2, Phase 3, Phase 4, and Phase 5 are accepted. Phase 6 and all
later phases have not been started.

## Phase 4 evidence

Phase 4 was executed only against the separate fixture directory
`fixtures/phase4_dji_0142_0_60`. The original video remained 193.593400 seconds
and the original SRT remained unchanged. The fixture video is 60.026633
seconds; its SRT spans `00:00:00,000` through `00:01:00,000` with 1,799 valid
cues. The fixture video SHA-256 is
`18d340d361b6d12e511233ba4ebdd0b6d8dd7024db39a48913f98fc4e7107d07`.

Both local and georeferenced preparation completed with 30 deterministic
frames at a 2-second sampling interval. The georeferenced asynchronous queue
run is persisted in `evidence/phase4/queue-state.json` and completed with
1,799 valid telemetry records, 30/30 matched frames, zero unmatched frames,
zero parser errors, and a maximum absolute association difference of
`0.003633` seconds. It generated `manifest.json`, `inspection.json`,
`preparation_report.json`, `telemetry/telemetry_report.json`,
`telemetry/association_manifest.json`, `geo.txt`, and prepared images. The
local route generated a manifest without `geo.txt` or telemetry output.

Phase 4: **ACCEPTED**. Phase 5: **ACCEPTED**. Phase 6 and all later phases have
not been started.

## Phase 2/3 implementation evidence

The live runtime used was the already accepted untouched WebODM 3.3.0 /
NodeODM stack. A direct adapter check returned project `2`, online-node health
`True`, completed status `40` for the accepted Phase 1 task, and successfully
retrieved `report.pdf`. The real adapter-backed `runner.run` submitted and
completed task `bc217fa8-a5c7-48ff-ad4a-aa7fa969fe58` through the adapter.

The persisted JobStore reservation remains atomic at the SQLite boundary:
existing task identities are reused, conflicting identities are rejected,
restart/replay does not submit again, and failed submissions move to a retryable
state. Existing failure, cancellation, partial, and recovery behavior remains
covered by the lifecycle and runner tests.

## Phase 5 orchestration and recovery evidence

Phase 5 is **ACCEPTED**. `run_reconstruction` now uses `WebODMAdapter` for
authentication, project selection, submission, status polling, cancellation,
output retrieval, and asset downloads. The existing SQLite JobStore persists a
logical submission fingerprint, project ID, and WebODM task ID before/after
submission; restart/replay reconciles that identity rather than submitting a
second task.

Focused Phase 5/recovery tests passed (`12 passed`). Live WebODM evidence:

- Successful recovery run: task `1f96fc44-d13d-4479-aa46-2d8ebc827631`,
  completed with 12 artifacts.
- Restart invocation reused the same task ID with no second submission.
- Active cancellation: task `cfe8cb83-f260-472d-bf3d-c33d59c02269`, terminal
  cancellation report preserved.
- Processing failure: task `6b75b5dd-fdce-4206-96d7-9fdb1f1a6acb`, genuine
  `Not enough memory` failure classified as `memory`; a retry invocation
  reconciled the same task and preserved the actionable failure state.

Failure reports, API logs, processing logs, task status, run manifests, and
partial outputs remain in their respective `evidence/phase5` run directories.
WebODM remains untouched. Phase 6 and all later phases have not been started.

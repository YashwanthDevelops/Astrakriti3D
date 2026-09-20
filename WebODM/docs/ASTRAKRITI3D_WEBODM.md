# Astrakriti3D WebODM integration

This document records the first maintained-fork/plugin boundary for the
Astrakriti3D product goal. It deliberately distinguishes code-level coverage
from live WebODM verification.

## Version and boundary

- WebODM source directory in this repository: `WebODM/`
- Maintained branch: `codex/astrakriti3d-webodm`
- Current source pin: `2e26f5321e6bcccab91662c024d2c0a9bbea2d9d` (record the
  deployed commit separately if the fork is rebased before release).
- Astrakriti3D is mounted as the `coreplugins/astrakriti3d` plugin.
- WebODM remains authoritative for users, sessions, Project permissions, Task
  lifecycle, processing-node assignment, native MapView, native Potree
  ModelView, artifacts, downloads, and `Task.potree_scene`.
- The plugin owns only the surrounding evidence-workspace presentation and
  the missing durable store for Map measurements.
- The legacy Astrakriti Flask dashboard UI is retired. Its root route redirects
  to the configured WebODM `/astrakriti/overview/` shell; if `WEBODM_BASE_URL`
  is missing or invalid, it returns HTTP 410 with setup guidance. Flask no
  longer serves the old static HTML/JavaScript assets. The read-only API
  endpoints remain for compatibility only; their SQLite records are not
  silently copied into a WebODM Project/Task.

The shell's route contract is rooted at `/astrakriti/` because WebODM's plugin
root mount mechanism is the supported extension point. Native viewer routes
remain inside the same authenticated WebODM application and use the existing
MapView/ModelView bundles; they do not redirect to a second dashboard.

The current shell exposes deep links for `/overview`, `/missions`, mission
context, run context, `/system`, and `/settings` under that plugin prefix. The
New Reconstruction page reserves a native Project/partial Task through the
plugin's retry-safe intake boundary, then uses WebODM's upload path and the
idempotent intake commit action, including upload progress. Before commit, it
loads a paginated candidate-frame review; the operator can retain all R1
frames, choose the recorded R2/coverage advisory set, or select a manual set.
The exact choice and candidate SHA-256 manifest are persisted on the intake
submission, then revalidated before excluded images are archived outside the
Task input root. For georeferenced video, `source_geo.txt` remains the immutable
source and root `geo.txt` is filtered to selected images. A browser reload can
resume review from the saved submission identity. A retry or lost response
therefore reconciles the existing native identity instead of creating a
second Task.
Video extraction, SRT parsing, and telemetry association are explicitly
`not_configured` when the protected Astrakriti preparation companion is not
deployed; the page does not invent those values. The optional
`docker-compose.astrakriti.yml` overlay deploys the preparation-only service
on the private Compose network. When configured, the WebODM server calls its
contract with a server-side bearer token, polls the real preparation state,
validates the returned bundle, copies the prepared frames/`geo.txt` into the
reserved native Task, and then uses the same idempotent native commit action.
The token and companion URL never reach browser code. The overlay's health
connectivity is live-verified; a complete upload-to-preparation-to-Task browser
journey remains unverified (see `ASTRAKRITI3D_LIVE_ACCEPTANCE.md`).

Optional server-only environment configuration:

- `ASTRAKRITI_COMPANION_URL` — private base URL for the preparation service.
- `ASTRAKRITI_COMPANION_TOKEN` — shared bearer secret; never place it in a
  template, browser bundle, query string, or log.
- `ASTRAKRITI_COMPANION_TIMEOUT` — bounded server request timeout in seconds
  (the health check uses a short three-second probe).
- `ASTRAKRITI_PREPARATION_MAX_MEMBERS` and
  `ASTRAKRITI_PREPARATION_MAX_UNCOMPRESSED_BYTES` — optional extraction safety
  limits for companion ZIP bundles (defaults: 100,000 files and 16 GiB).

Without both URL and token, the companion state is `not_configured` and the
still-image native intake remains available.

## Data mapping

| Product concept | WebODM/Astrakriti authority |
| --- | --- |
| Mission identity and display name/description | WebODM `Project` is the sole writable authority; one-to-one `AstrakritiMissionMetadata` adds location, capture context, and provenance without copying native fields |
| Run / reconstruction attempt | WebODM `Task` |
| Processing state | `Task.status`, `upload_progress`, `running_progress`, `last_error`, and native task actions |
| Prepared frames and telemetry review | Path-free `frames.json` and `telemetry.json` under the Task's private `data/astrakriti3d/` directory, created from the validated companion bundle; WebODM remains authoritative for the Task and uploaded frame files |
| Map / DSM / DTM | `Task.get_map_items()` and authorized tile/metadata endpoints |
| 3D scene | Native `Task.potree_scene` and `/api/projects/:project/tasks/:task/3d/scene` |
| Artifacts | Existing `Task.available_assets` plus verified files under WebODM task storage |
| Legacy Mission/Run/Job identity | `AstrakritiLegacyLink`, populated by the additive `astrakriti_reconcile` command; unresolved/conflicting records retain source payloads and are never guessed |
| Map measurement | `app.AstrakritiMeasurement`, associated to exactly one Project and Task |
| 3D measurement | Native Potree scene persistence; no parallel 3D authority is introduced |
| System health | Authenticated WebODM request, cached processing-node state, storage capacity, and explicit companion-service configuration state |
| Video/SRT preparation | Protected Astrakriti companion queue and manifest/bundle, linked to the WebODM submission identity; no competing WebODM Task lifecycle |

The measurement model stores stable identity, geometry, type, result metadata,
units, CRS/local-frame label, method, author, timestamps, schema revision, and
a revision derived from the real Task artifact inventory. A changed artifact
revision is surfaced as `stale`; it is never silently reattached to new output.

## API and action contract

- `GET/PATCH /api/plugins/astrakriti3d/mission/:project/metadata/` reads and
  updates only Astrakriti-owned location, capture context, and provenance for
  an authorized Project. Reads report `recorded: false` without creating a
  row. Writes require native `change_project`; Project name and description
  remain managed through WebODM.
- `GET /api/plugins/astrakriti3d/legacy/reconciliation/` exposes a paginated,
  read-only queue to WebODM staff. It includes identity labels, mapping state,
  reason codes, and native associations but excludes source paths and legacy
  payloads. Actual mapping remains an explicit `astrakriti_reconcile` command
  operation after reviewing exact Project/Task identities.
- `GET /api/plugins/astrakriti3d/measurements/task/:task/` returns only
  measurements for the authorized WebODM Task.
- `GET /api/plugins/astrakriti3d/preparation/task/:task/?view=frames` returns a
  paginated, searchable frame manifest with authorized WebODM thumbnail and
  download URLs. `view=telemetry` returns paginated parsed records plus parser,
  association, hash, warning, and limitation summaries. Both use the native
  task/project access check; page-local metadata is stored beneath the Task's
  private `data/astrakriti3d/` directory and is not exposed as a public file.
  Companion host paths and raw subtitle text are excluded from the browser
  response. Local/unreferenced preparation returns `not_applicable` telemetry;
  Tasks without an imported manifest report `unavailable` rather than inferred
  timestamps or quality scores.
- `POST` to that endpoint accepts `name`, `measurement_type`, a GeoJSON
  `LineString` or `Polygon`, `result`, `units`, `crs`, and `method`. It returns
  `201` with the stable measurement record; malformed geometry, missing DSM
  extent for volume, and unauthorized writes return a validation/permission
  error.
- `PATCH` and `DELETE` on
  `/api/plugins/astrakriti3d/measurements/task/:task/:measurement/` rename or
  remove the task-scoped record and require the native Project change
  permission (unless WebODM's explicit public-edit policy applies). A PATCH
  may include the returned `updated_at` as `expected_updated_at`; a stale
  concurrent editor receives HTTP `409` and the shell exposes the conflict
  instead of overwriting newer geometry/name state.
- `GET /api/plugins/astrakriti3d/measurements/task/:task/export/` returns
  coordinate-preserving JSON by default or validated geographic GeoJSON when
  every record is EPSG:4326-compatible.
- Native WebODM `POST` actions remain authoritative for cancel/restart:
  `/api/projects/:project/tasks/:task/cancel/` and `/restart/`. The shell only
  exposes them when the serialized Project permission allows the action and
  reloads from the Task record after acceptance.
- New Reconstruction reserves through `POST
  /api/plugins/astrakriti3d/intake/reserve/`, keyed by a durable client
  idempotency key and a request/file-selection fingerprint. The endpoint
  applies native Project permissions, creates at most one Project and partial
  Task, and returns the existing identities on a safe retry. Images then use
  native `POST /api/projects/:project/tasks/:task/upload/`.
- Before commit, `GET` and `POST
  /api/plugins/astrakriti3d/intake/:submission/selection/` expose the authorized
  paginated candidates and persist a validated frame set. The record includes
  candidate hashes, a canonical set hash, strategy, and source-geo hash. Commit
  rejects stale/changed inputs, archives excluded frames under Task evidence,
  filters `geo.txt` from the preserved source, and records applied hashes. The
  UI defaults to R1/all frames; R2 and coverage remain explicit experimental
  recommendations rather than silent automatic filtering.
- The final step uses `POST
  /api/plugins/astrakriti3d/intake/:submission/commit/`. The server locks the
  Task, commits it once, and enqueues native processing only after the database
  transition; a repeated commit returns the same Task without a second worker
  enqueue. A failed request leaves any already-created native record intact and
  identifies the failing step.
- When the companion is configured, `POST
  /api/plugins/astrakriti3d/intake/:submission/prepare/` sends the source video
  and optional SRT server-to-server; `GET` on the same route observes the
  preparation queue. `POST
  /api/plugins/astrakriti3d/intake/:submission/import/` downloads the completed
  bundle, validates ZIP paths, manifest/frame identity, and input mode, then
  copies only prepared images plus an optional `geo.txt` into the reserved
  native Task. A partial or unavailable preparation never commits the Task.
  Incoming video/SRT multipart bodies are staged into request-owned files
  before the server-to-server request so Django temporary-upload lifecycle
  cleanup cannot produce a closed-file handoff failure.

Run and processing context pages poll the native Task detail endpoint every
five seconds while visible, stop the timer on navigation/hidden state, and
reload only when the authoritative status, progress, error, or artifact
inventory changes. Native MapView and Potree pages are excluded from this
reload loop so viewer camera/tool state is not interrupted.

## Extension and fork register

| Change | Reason | Regression surface |
| --- | --- | --- |
| `coreplugins/astrakriti3d` | Add the shell, context routes, native viewer host pages, health summary, and measurement API | Plugin loading, authenticated route tests, native MapView/ModelView browser tests |
| `app/models/astrakriti3d.py` + migrations `0053_astrakriti_measurement` through `0057_astrakriti_mission_metadata` | WebODM's existing plugin data store is user/global key-value storage and cannot enforce Project/Task ownership, Mission metadata association, durable intake idempotency, companion preparation provenance, or auditable legacy identity links | Migration, CRUD, permission, export, stale-revision, task-isolation, duplicate-reservation, idempotent-commit, preparation-state, and reconciliation tests |
| `coreplugins/astrakriti3d/companion.py` and Astrakriti `astrakriti3d/companion_api.py` | Provide a protected preparation-only server boundary without exposing credentials or creating a second Task lifecycle | Bearer authentication, source-hash idempotency, ZIP safety, queue status, and unavailable-state tests |
| `coreplugins/astrakriti3d/api.py` upload staging | Keep the protected server-to-server multipart handoff readable for large Django temporary uploads | Closed-temporary-upload regression plus live HTTP video/SRT preparation/import |
| `coreplugins/astrakriti3d/api.py` optimistic measurement PATCH and `public/shell.js` action status | Prevent stale concurrent editors from silently overwriting a newer task-scoped measurement and expose retry/conflict outcomes inline | Targeted HTTP `409` regression plus two live browser contexts, failed-save retry, and browser-delete evidence |
| `coreplugins/astrakriti3d/api.py` preparation review persistence/read API and `public/shell.js` Frames/Telemetry views | Preserve validated frame/telemetry evidence across restart and make it available only through the authorized WebODM Task boundary | Bundle-import regression, path-redaction check, pagination/filter checks, and browser frame/telemetry review |
| `coreplugins/astrakriti3d/api.py` intake frame-selection persistence and `public/shell.js` New Reconstruction review | Require an explicit, durable input set before native processing; preserve candidate/source hashes and selected-image/geo parity | Manual/R1/R2/coverage selection, stale-input and owner checks, excluded-image archive, geo filtering, retry, and reload tests |
| Astrakriti `project.py` selection advisory generation and pinned companion OpenCV dependencies | Run the existing adaptive and georeferenced coverage selectors as path-free, non-mutating recommendations while retaining every R1 source frame and the authoritative `geo.txt` | Synthetic video preparation, selector/preparation suite, coverage parity/preservation regression, and path-redaction checks |
| `coreplugins/astrakriti3d/api.py` selector evidence whitelist and `public/shell.js` Frame Review metrics | Present measured proxies and per-frame R2/coverage recommendations as experimental evidence; never imply that recommendations change the submitted input set | Bundle-import API regression, preview/metadata authorization tests, copy/path sanitization, keyboard/focus and responsive UI verification |
| `coreplugins/astrakriti3d/public/astrakriti.css` reduced-motion media rule | Make the customized WebODM shell and native viewer page honor `prefers-reduced-motion` without replacing native viewer behavior | Live reduced-motion DOM audit at the Map workspace |
| `coreplugins/astrakriti3d/public/astrakriti.css` route-shell bottom padding override | Remove the inherited 8px `#page-wrapper` tail that caused desktop Overview overflow without changing upstream WebODM styles | Live document-size and computed-style checks at `1440×900`, `1280×800`, `768×900`, and `390×844` |
| `coreplugins/astrakriti3d/views.py` shell permission translation | Convert the WebODM permission helper's DRF `NotFound` into Django `Http404` when a private Project is requested through a normal page view | Private real-Task route returns 404, plus `test_private_task_workspace_returns_not_found` |
| `app/models/__init__.py` | Register the focused model with the WebODM app | Django model discovery and migration checks |
| `coreplugins/measure/volume.py` | Reject selected polygons that intersect DSM NoData/incomplete coverage; convert horizontal and vertical axes separately; qualify inferred Z units and unknown vertical datum | Synthetic NoData/unit regressions plus historical live real-DSM valid, NoData, base-method and independent-control checks |
| `coreplugins/measure/api.py` | Apply WebODM Task visibility checks and a short-lived signed Task/job binding to DSM-volume status/result reads; retain numeric output and return unit provenance separately | Authorized result/context and status tests; foreign-user private-Task and cross-Task job-binding `404` regressions; live missing-token denial |

No native viewer engine, authentication system, processing scheduler, or task
state machine was replaced. The WebODM upstream revision must be recorded in a
release manifest before deployment. Rebase/release procedure: export the
measurement JSON/GeoJSON, back up the database and media volume, rebase the
plugin/model patch onto the pinned upstream revision, run migrations and the
WebODM test suite, then repeat the real-task viewer/measurement gate.

## Migration and rollback

1. Back up the WebODM PostgreSQL database and media volume.
2. Apply `python manage.py migrate` so migrations `0053` through `0057` create
   additive measurement, intake-submission, preparation evidence, legacy-link,
   and one-to-one Mission metadata tables. Existing Projects remain valid and
   report Mission context as not recorded until an authorized user supplies it;
   no Project name, description, or historical identity is inferred or copied.
3. Preview legacy reconciliation without writes:

   ```powershell
   python manage.py astrakriti_reconcile --source C:\path\to\jobs.sqlite3
   ```

   Supply `--identity-map C:\path\to\identity-map.json` when the legacy
   source does not contain an exact native Project/Task ID. Review the JSON
   preview, then repeat with `--apply`; the command is resumable and never
   creates a native Project/Task or guesses by display name. Unresolved and
   conflicting records remain visible as `reconciliation_required` or
   `conflict` links with their original payload and source path preserved.

   The identity-map shape is intentionally explicit:

   ```json
   {
     "missions": {"legacy-mission-id": "webodm-project-id"},
     "runs": {"legacy-run-id": "webodm-task-uuid"},
     "jobs": {"legacy-job-id": "webodm-task-uuid"},
     "projects": {"legacy-project-id": "webodm-project-id"}
   }
   ```
4. For rollback, first export/delete only measurements or link records created by the current
   deployment if required, restore the database backup, and remove the plugin
   or migrate back to `0052_grid_shift_correction`. A rollback after users have
   created measurements is data-affecting and must not be run without the
   backup/export step.

## Verification status

### DSM volume units and limitations

DSM volume is reported in `m³` only when its horizontal CRS is projected and
has a usable linear-unit conversion. Horizontal pixel area is converted by
the CRS factor squared; elevation differences are converted independently
using the raster-band unit when declared. An absent band unit is not silently
treated as a known metre value: for projected ODM DSMs the implementation
explicitly assumes the Z unit matches the projected CRS linear unit and saves
that assumption with the result. The vertical datum remains `unknown`; the UI
and saved measurement disclose this limitation. The volume-result endpoint
keeps its existing numeric `output` field and adds `unit_context` separately
for compatibility. Unsupported declared band
units and geographic/no-linear-unit CRSs are rejected instead of producing a
misleading cubic-metre result. This assumption does not establish absolute
elevation accuracy or a vertical datum.

Static and live evidence are recorded separately. Static checks and the
focused Django/Astrakriti3D suites pass in the current Docker deployment. The
real completed Task MapView/Potree/measurement gate also has a concrete
evidence record, including independent numerical controls, reload/restart,
permission, and parsed export results:

`docs/ASTRAKRITI3D_LIVE_ACCEPTANCE.md`

That record is authoritative for the current resumed run. It explicitly lists
the remaining unsupported and blocked portions of the larger product goal;
this document does not claim the overall goal is complete.

### Native Map/Potree accessibility fork patch

The WebODM-owned MapView/Potree engines remain in place. The focused upstream
vendored-source patch is in `app/static/app/js/components/Map.jsx`,
`app/static/app/js/ModelView.jsx`, `app/static/app/js/components/AssetDownloadButtons.jsx`,
and `app/static/app/js/vendor/potree/build/potree/{potree.js,potree.css,sidebar.html}`.
It supplies a named Map region and associated opacity labels; turns Potree's
icon-only measurement, clipping, and navigation actions into named native
buttons; assigns slider roles/names/values to jQuery UI handles; gives the
canvas a normal tab position, visible focus, and a Task-title description; and
names the icon-only asset-download action. The corresponding focused Jest
coverage and live Tab/DOM evidence are recorded in
`ASTRAKRITI3D_LIVE_ACCEPTANCE.md`.

For upgrades, compare this small source patch with the exact pinned WebODM
upstream revision before rebasing. Keep the Potree license and vendored
provenance intact; rebuild WebODM Webpack/static files, run the focused Map and
download tests, then verify the native controls in a browser. Do not manually
patch generated bundles or bypass WebODM's normal static collection. This
bounded patch does not establish full application accessibility compliance.

The selector path is now present in the running companion. On 2026-09-20 the
companion was rebuilt from the current `Astrakriti3D` source and recreated
without changing its persistent `webodm_astrakriti_companion_data` volume. The
running `/opt/astrakriti/astrakriti3d/project.py` SHA-256
(`3db9ac46205e7febefa2bebc741ce8b0313a9b576f16a299eb6467a7a50d6b2a`) matches
the source; authenticated `/health` returned HTTP 200 / `ready`, and the four
existing preparation-queue records remained `completed`. The focused local
preparation/selection suites passed `11/11` immediately before deployment.
This closes the stale-image/deployment discrepancy, not the broader live
acceptance gate: no new WebODM Project or Task was created for this deployment
check, and advisory recommendations still require suitable video/telemetry
input to be demonstrated in a live browser flow.

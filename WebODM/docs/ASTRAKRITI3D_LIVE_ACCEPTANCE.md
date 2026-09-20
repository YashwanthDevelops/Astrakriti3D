# ASTRAKRITI3D live acceptance gate

Date: 2026-09-19 (Asia/Calcutta)

This is the evidence record for the live gate in
`C:\Users\Yashwanth\ai mentor\AI-HARNESS-GOAL.md`. It records the current
Docker deployment and one real completed WebODM Task. It does not turn
unexercised goal criteria into success.

## Environment and deployment

| Check | Action and evidence | Status |
| --- | --- | --- |
| Docker runtime | `docker info --format 'Server={{.ServerVersion}} Containers={{.ContainersRunning}} Driver={{.Driver}}'` returned `Server=29.8.0 Containers=5 Driver=overlayfs`; Docker server was `desktop-linux`. | PASS |
| Services | `docker compose -f docker-compose.yml ps` showed `webapp`, `worker`, `db`, `broker`, and `node-odx-1` running. WebODM exposed `localhost:8000`. | PASS |
| Plugin startup | `docker logs webapp` reported WebODM `3.3.0` and `INFO Registered [coreplugins.astrakriti3d.plugin]`. | PASS |
| Django health | `docker exec webapp python manage.py check` returned `System check identified no issues (0 silenced).` | PASS |
| Migrations | `docker exec webapp python manage.py showmigrations app` showed `[X]` for `0053_astrakriti_measurement`, `0054_astrakriti_submission`, `0055_astrakriti_preparation`, and `0056_astrakriti_legacy_link`. | PASS |
| Astrakriti3D tests | `python -m pytest -q` in `C:\Users\Yashwanth\SIH Project\Astrakriti3D`: `145 passed in 34.04s` on the latest run before the WebODM-only shell permission fix. Astrakriti3D source was not changed afterward. | PASS |
| WebODM plugin tests | Latest `docker exec webapp python manage.py test app.tests.test_astrakriti3d -v 0`: `Ran 13 tests in 4.616s ... OK`, including NoData/incomplete coverage, closed-upload staging, stale measurement conflict, and private shell 404 regressions. | PASS |
| JS syntax | `node --check coreplugins/astrakriti3d/public/main.js` and `shell.js`: no errors. | PASS |
| Diff hygiene | `git diff --check`: PASS. Temporary `Dockerfile.astrakriti3d.local` was deleted and `Test-Path` returned `False`. | PASS |

The image was built from the maintained WebODM base (`2e26f5321e6bcccab91662c024d2c0a9bbea2d9d`) plus the working-tree Astrakriti3D plugin/model/migration changes. The source changes are intentionally not presented as a clean release commit; the working tree contains the user’s existing uncommitted implementation files and they were preserved.

### Fresh post-rebuild runtime recheck

The resumed recheck after the focused DSM rebuild produced the following new
evidence without modifying the real Project or Task:

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Container and schema recheck | `docker compose ps` showed all five services (`webapp`, `worker`, `db`, `broker`, `node-odx-1`) running; `manage.py check` passed; migrations `0053` through `0056` were `[X]`; `app.tests.test_astrakriti3d` ran 12 tests and returned `OK`. | PASS |
| Deployment source check | The running `webapp` contains the NoData/incomplete-coverage guard in `coreplugins/measure/volume.py`; `Dockerfile.astrakriti3d.local` is absent from the working tree. | PASS |
| Real Task identity and layers | Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6` remained status `40`, `partial=False`, with artifact revision `043f46bc045268ec9fffc375a46bf3f846817a44b097336b4ffa809250e216b7`; `get_map_items()` returned `orthophoto`, `plant`, and `dsm` tiles with EPSG `32615`. | PASS |
| Real artifact delivery recheck | Native download endpoints returned `200`: `orthophoto.tif` 5,399,469 bytes, `dsm.tif` 3,233,191 bytes, `georeferenced_model.laz` 2,833,794 bytes, and `report.pdf` 9,249,966 bytes. | PASS |
| Native Potree recheck after latest recreate | An isolated authenticated viewer session reopened the real Task Model route after the application-service recreate. The route stayed on the real Task URL, `#potree_render_area` contained a visible `396×665` canvas after load, the native Cameras/Appearance/Tools/Clipping/Scene/Filters controls were present, and no console errors were observed in this recheck. The disposable viewer account was removed and the real Task remained. | PASS |
| DSM calculation recheck | Direct live calculation on the real `dsm.tif` returned `triangulate=0.4701`, `plane=0.5241`, `average=0.5239`, `highest=15.7946`, `lowest=10.7557`; the recorded NoData footprint returned `Selected footprint intersects NoData or incomplete DSM coverage`. | PASS |
| Protected video/SRT preparation and import | With an isolated bearer-protected companion and real HTTP multipart requests, a disposable reservation returned `201` for Project `13` / Task `b30fbb92-1e7f-476f-8664-a061b88a87f2`; the 5.005-second, 101,026,331-byte clip was derived from the real `DJI_0142.MP4` and paired with the real 1,691,677-byte `DJI_0142.SRT`. Preparation returned `202`, progressed `running → completed`, produced 5 frames, matched all 5/5 telemetry records within the 0.5-second tolerance, reported EPSG:4326 and `geo.txt`, and import returned `200` with `imported=true`, `frame_count=5`, and `status=imported`. Native project deletion returned `204`; guarded cleanup verified the disposable Project, Task, submission, and user were absent. | PASS |
| Acceptance-run residue | Database inspection returned no temporary acceptance users, no temporary projects, and zero `AstrakritiSubmission` rows; the real Project `2` and Task remained present. | PASS |

This recheck confirms the deployment is healthy after restart/rebuild, but it
does not replace the browser-only or companion-service cases marked below as
`UNSUPPORTED` or `BLOCKED`.

### Playwright exact viewport and browser upload gate

Because the in-app browser could not resize or attach local files, a temporary
Playwright `1.63.0` runner using the installed system Chrome was used for this
browser-level check. The temporary spec and screenshots were stored outside
the repository and removed after the run; the package remains outside the
repository under the task-specific `%TEMP%` directory, and no browser
dependency was added to the project.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Required viewport route audit | `node C:\Users\Yashwanth\AppData\Local\Temp\astrakriti3d-playwright-gate\node_modules\@playwright\test\cli.js test qa/live_gate.spec.cjs --reporter=line --workers=1` exercised 9 global/project/task routes at all four required sizes: `1440×900`, `1280×800`, `768×900`, and `390×844` (36 route/viewport combinations). Every route retained its intended URL and Astrakriti shell; each reported `scrollWidth == clientWidth` at the exact viewport. | PASS for exercised route/viewport matrix |
| Browser file selection and native intake | Playwright `setInputFiles` attached real `frame_000001.jpg` and `frame_000002.jpg`; the UI reached `/astrakriti/runs/cfb11d36-6860-46ac-9eaf-d666a4c83a0a/`, native reservation response was `201`, and the browser-issued cancel request returned `200`. Server inspection showed Project `14`, Task status `50` (canceled), `partial=False`, and `images_count=2`. | PASS |
| Browser console and network failures | The same run collected `consoleErrors=[]` and `requestFailures=[]` across the route audit and intake flow. | PASS |
| Screenshot/reference comparison | The temporary runner captured overview screenshots for each required viewport, but this run recorded structural/overflow evidence only; a full human comparison against every approved reference remains undone. | VERIFICATION GAP |
| Screenshot archive via the in-app browser | The in-app browser exposes transient screenshot bytes but no supported workspace-save operation. This is a tooling limit, not a product failure. | UNSUPPORTED (archive mechanism only) |

### Latest measurement reliability, deletion, and motion gate

After the concurrency/API update and application-service recreate, a temporary
Playwright run used the real Task and a disposable authenticated browser
account. It did not retain any measurement on the real Task.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Browser-native delete | A real saved row was opened in the Measurements workspace; clicking its UI `Delete` button raised the native confirmation `Delete this saved measurement?`, accepted confirmation removed the row, and the follow-up task-scoped GET returned `200` with `[]`. | PASS |
| Failed save and retry | A real map LineString measured `20.345848705042215 m`. The first task-scoped measurement POST was deliberately aborted at the browser boundary; the inline button changed to `Failed to fetch` and became enabled. Retrying the same popup returned `Saved`, one persisted record with the same geometry/value was observed by GET, and cleanup returned `204`. | PASS |
| Concurrent editor conflict | Two live browser contexts loaded the same `updated_at`. Editor A PATCH returned `200` and `name=Editor A`; the stale Editor B UI PATCH was rejected with `409`, the row visibly reported `This measurement changed in another editor. Reload the latest saved geometry before editing it again.`, and the final GET retained `Editor A`. Cleanup returned `204`. | PASS |
| Reduced motion | Playwright emulated `prefers-reduced-motion: reduce` on the Map workspace. `matchMedia` was `true`; the DOM audit found `violationCount=0` for transition/animation durations over `0.011s` or infinite/multi-iteration animation. | PASS |

The save-failure run intentionally produces one failed-request console entry;
it is not used as the clean-console result. The same Map load also reported two
native Leaflet marker data-URL warnings (`marker-icon.png` and
`marker-shadow.png`); this is recorded as a native WebODM/Leaflet warning, not
silently counted as a clean-console PASS. The route-matrix console result above
remains limited to its exercised routes and non-injected requests.

### Latest first-use and context-navigation gate

An isolated user with no pre-existing Astrakriti project permissions used the
live browser against the deployed application. The native Project/Task created
by this run was canceled and deleted through the normal API path; the source
Task `2` and Project `2` were not involved.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| First-use shell | A fresh authenticated user opened `/astrakriti/overview/` with the `OVERVIEW` heading and New Reconstruction actions, then opened `/astrakriti/new-reconstruction/` with the `NEW RECONSTRUCTION` heading. | PASS for first-use route reachability; a full empty-state copy matrix remains UNSUPPORTED |
| Real browser create | Playwright `setInputFiles` selected `DJI_0177.JPG` and `DJI_0176.JPG`; the form reserved Project `15` / Task `7ce8ff32-27ca-4493-9867-6ac2b4e5021f` with HTTP `201`, committed with HTTP `200`, and navigated to the real Run Overview. | PASS |
| Deep-link reload | Reloading the created Run URL retained `RUN OVERVIEW`, the same URL, and the real `First-use Gate Run` identity. | PASS |
| Back/forward context | Browser Back returned to `/astrakriti/new-reconstruction/` with `NEW RECONSTRUCTION`; Forward returned to the same Run Overview URL and heading. | PASS |
| Safe cleanup | Native cancel returned `200`; Project deletion returned `204` and completed asynchronously. Final guarded cleanup verified Project `15`, Task `7ce8ff32-27ca-4493-9867-6ac2b4e5021f`, submission `a5af6b22-134e-4b8d-b0a8-c91b66ff7720`, and the disposable user were absent. | PASS |

## Latest resumed browser gate

The resumed browser audit used the temporary authenticated owner account
`audit_owner_2026` against the live `localhost:8000` deployment. The account
was granted only the project-view/change/delete permissions needed for this
audit and was not used to alter the real Project/Task artifacts.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Route and shell audit | At the available desktop viewport (`innerWidth=1280`, `innerHeight=720`, `devicePixelRatio=1.25`, document `scrollWidth=1265`, client width `1265`), global Overview, Missions, Reconstructions, Artifacts, Reports, Processing, System, Settings, and New Reconstruction routes rendered their intended shell/headings. Project Overview, Runs, Artifacts, Reports, and Files routes rendered for Project `2`. Task Overview, Processing, Frames, Telemetry, Measurements, Validation, Reports, and Files routes rendered for the real Task. | PASS |
| Mission runs and processing | `/astrakriti/missions/2/runs/` rendered `MISSION RUNS`, active project navigation, and 5 real run links. `/astrakriti/processing/` rendered `PROCESSING / RECOVERY`, 5 real run links, and explanatory recovery text without a fabricated run context. | PASS |
| Search and sort | Missions search for `Phase 1` produced `?q=Phase+1` with one matching real row. Selecting name ascending produced `&sort=name_asc` and the selected state persisted in the response. | PASS |
| New Reconstruction validation | The live form exposed labelled mission/run/input/preparation fields and a real `Validate and start reconstruction` action. Activating it empty showed `Input needs attention` with the actual requirements for a task name/new project, stills, and SRT where applicable; no submission side effect occurred. Video/SRT preparation remained visibly disabled because the companion is not configured. The later Playwright gate attached real still files with `setInputFiles`, reserved a native Task, and canceled it with server-confirmed cleanup. | PASS for validation and browser file selection; companion path is separately evidenced when configured |
| Native still intake and cancellation | Supported live boundary test with disposable Project `6` and Task `235f182b-8d31-43a0-a72c-dfcbbfce633c`: reserve `201`, upload `200` (`DJI_0177.JPG` and `DJI_0176.JPG`, 5,222,839 and 5,176,728 bytes), commit `200`; the browser Run Overview showed `PROCESSING`, `Frames 2`, native Map/3D/log links, and then, after the cancel endpoint returned `200`, showed `CANCELED`, `Restart task`, and 6 real output files after reload. | PASS for supported native intake/cancel; exact browser file selection is PASS in the Playwright gate above |
| System health | Live accessibility state showed WebODM `CONNECTED`, Workers `UNKNOWN` with an honest explanation, `node-odx-1: connected`, storage `932.7 GB free of 1006.9 GB`, and companion `NOT_CONFIGURED`. Refresh changed the health timestamp while preserving the live values. | PASS |
| Accessibility and overflow sample | No missing image alt text was found. Frame links had accessible names such as `DJI_0176.JPG`; shell navigation, Settings, New Reconstruction, and run links were reachable by Tab with visible active focus. The Playwright route matrix reported no horizontal overflow at all four required viewports; the full accessibility matrix remains UNSUPPORTED. | PASS for exercised route matrix |
| Console | `auditTab.dev.logs({levels:["error","warn"],limit:200})` returned `[]` during the route and viewer audit. | PASS |
| Missing DSM negative path | A disposable Task `6184f15b-70fc-4c80-990e-3b6593246beb` under the real Project returned HTTP `400` for a volume request with detail `volume measurements require a task with a valid DSM extent`; the disposable Task was deleted afterward. | PASS |
| DSM coverage and base-surface matrix | After the focused native `coreplugins/measure/volume.py` guard was deployed, the real DSM API route returned a worker result of `0.4701` for a complete-coverage `triangulate` footprint; the same footprint returned `0.5241` (`plane`), `0.5239` (`average`), `15.7946` (`highest`), and `10.7557` (`lowest`). A real NoData API request completed with `/api/workers/check/…` = `{"ready":true,"error":"Selected footprint intersects NoData or incomplete DSM coverage"}` instead of silently producing `0.0`. | PASS for valid/NoData/base-method behavior; unknown vertical-unit metadata remains UNSUPPORTED |
| Submission idempotency | A disposable intake reservation returned `201` on the first request, `200` with `reused=true` and the same Task on the repeated request, and `409` for the conflict payload. The disposable submission/Task was deleted afterward. | PASS |
| Concurrent duplicate reservation | Two simultaneous live reservation requests for disposable user `race_owner_2026` returned exactly `[200, 201]`, both referenced Task `d390d9b3-a3dc-439f-b319-20e2428248d0`, and the database contained one submission row. Project `10`, Task, submission, and user were removed through guarded cleanup. | PASS |
| Private/public permission matrix | On disposable Project `7` / Task `0c887e5c-ad2a-4639-9af1-f451d4e06ba7`, owner GET was `200`; private viewer and anonymous GET were `404`; after enabling public read-only, viewer GET was `200` but viewer POST was `404` and anonymous GET was `200`; after explicitly enabling public edit, the authenticated viewer POST/PATCH/DELETE returned `201/200/204`. The disposable project, task, measurement, and users were removed through guarded cleanup. | PASS |
| Artifact delivery | Authenticated Django client downloads returned `200`: `dsm.tif` (`image/tiff`, 3,233,191 bytes), `orthophoto.tif` (`image/tiff`, 5,399,469 bytes), `georeferenced_model.laz` (`application/zip`, 2,833,794 bytes), and `report.pdf` (`application/pdf`, 9,249,966 bytes). | PASS |
| Disposable Task output discovery | The newly committed disposable Task’s reloaded Run Overview listed `cameras.json`, `georeferenced_model.laz`, `orthophoto.tif`, `report.pdf`, `shots.geojson`, and `textured_model.glb`, each with a real size and download link. | PASS |

The in-app browser was not used for exact viewport resizing; the temporary
Playwright run above is the authoritative evidence for the four required
viewport sizes. The older 1280-wide in-app snapshot below is retained only as
context and is not substituted for that matrix.

## Fresh continuation gate — 2026-09-19

This is the live evidence gathered after Docker Desktop was restarted. It is
later than the earlier traces above. The audit account had no permission on
private Project `2`; no permission was added to that real Project, and neither
the real Project nor Task was modified.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Docker runtime and services | `docker info` returned `Server=29.8.0 Containers=5 Driver=overlayfs`; `docker compose ps` showed `webapp`, `worker`, `db`, `broker`, and `node-odx-1` running after application-service recreation. | PASS |
| Standard full image build | This historical attempt failed at `Dockerfile:128`, stage `[app 1/5]`, with `E: Invalid operation update` from `apt-get -qq update`; the same operation exited `0` in a clean `ubuntu:22.04` container. A later standard full build completed successfully on 2026-09-20 (see the current build recheck below). | PASS (later standard build succeeded) |
| Scoped runtime deployment | A third derived layer copied only `app/models/astrakriti3d.py` with explicit index names matching the already-applied migrations. `webodm/webodm_webapp:latest` and both app services now use image `sha256:ffac2b24eb7585dddf619ef54a18cba6f7309a6b79d7af10c27c299418ce0563`; rollback tag `pre-migration-index-alignment-20260919` retains the immediately prior image, alongside `pre-overflow-fix-20260919` and `css-overflow-fix-20260919`. | PASS |
| Django/schema/tests | Fresh post-restart `manage.py check` reported no issues; migrations `0053`–`0056` were all `[X]`; after model/migration index alignment, Compose-context `makemigrations --check --dry-run` returned `No changes detected`; `app.tests.test_astrakriti3d` returned `Ran 13 tests in 4.745s ... OK`, including the private-workspace 404 regression. `docker inspect webapp worker` reported the same new image ID for both services: `sha256:ffac2b24eb7585dddf619ef54a18cba6f7309a6b79d7af10c27c299418ce0563`. | PASS |
| Desktop Overview overflow | With the first-use Overview at `1440×900`, document `scrollWidth/clientWidth=1440/1440`, `scrollHeight/clientHeight=900/900`, `#page-wrapper` bottom `900`, and computed bottom padding `0px`. At `1280×800` the dimensions were `1280/1280` and `800/800`; at `768×900` they were `768/768` and `900/900`. | PASS |
| Narrow Overview | At `390×844`, document `scrollWidth/clientWidth=375/375` (no page-level horizontal overflow) and `scrollHeight/clientHeight=1074/844` (normal vertical content scroll). The global navigation and utility strip are internal horizontal scrollers; trailing items require horizontal scrolling. | PASS |
| Real Task identity after recreation | Read-only ORM inspection still found Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6`, `Morris Thomas Road - 01/08/2016`, status `40`, Project `2`, with `orthophoto.tif`, `dsm.tif`, `georeferenced_model.laz`, `textured_model.glb`, and the other listed native outputs. Project `2` remains private, Task public read-only. The current measurement row count is `0` after the earlier acceptance cleanup. | PASS |
| Migration-state reconciliation | The first model/state comparison proposed six index-name changes because model Meta indexes were implicit while applied migrations define explicit names. The model now declares the six existing migration names; Compose-context `makemigrations --check --dry-run` reports `No changes detected`. No `0057` migration was generated or applied and no database index was changed. | PASS |
| Audit-user cleanup | Guard checks found the two disposable audit accounts owned zero Projects, Tasks, measurements, or submissions before deletion; both accounts were removed. The real Project `2` and Task were retained. | PASS |
| Private Astrakriti Task route | Before the fix, `/astrakriti/runs/<task>/map/` rendered HTTP 500 because `check_project_perms` raised DRF `NotFound` inside a normal Django view. The shell now translates that denial to Django `Http404`; the targeted test passes and a browser reload of the same real route rendered WebODM `404 Page Not Found`, with no permission change. | PASS |
| Real native MapView | After the final migration-alignment image restart (`sha256:ffac2b24…`), `/public/task/<task>/map/` showed the real orthophoto pixels; reloading that route reproduced the raster within 3 seconds. The Measure panel exposed “Measure volume, area and length”, “Create a new measurement”, and “Export Measurements”; browser `error`/`warn` logs were `[]`. The private Astrakriti shell route remains inaccessible to this no-project-permission account. | PASS |
| Real native Potree | After the same final restart, `/public/task/<task>/3d/` showed the actual point-cloud geometry in `potree_render_area`, with native point/distance/area/volume/height and clipping tools. A browser reload reproduced the geometry within 5 seconds; current `error`/`warn` logs were `[]`. | PASS |
| Distance, area, DSM volume, persisted records, and parsed export | The preceding owner-session gate records the real distance `18.99338307861003 m` (independent control `18.971120066388 m`, `0.117%` delta), area `102.62 m²` (control `103.131836 m²`, `0.499%` delta), and DSM volume `45.2516 m³` (control `45.744096 m³`, `1.088%` delta). Its stable IDs `a451e8d9-72ec-4537-a31c-0628a59d2006` and `f43c4f93-de32-45b7-9246-44ea14214c7b` survived browser reload and service recreation before the test records were deliberately removed. Parsed GeoJSON returned HTTP `200` with two features matching those IDs and their stored properties. | PASS |
| Fresh measurement-persistence replay | The accepted Task currently has zero measurement rows because the disposable acceptance rows were deliberately cleaned. The previously captured real measurement, browser reload, service recreation, permission, and parsed-export evidence above remains valid. This turn did not repeat that sequence against the accepted Task. | VERIFICATION GAP (fresh replay only; prior behavior remains PASS) |
| Viewer export download event | The server-parsed GeoJSON is PASS as recorded above, but a browser-native download event remains unobserved. | UNSUPPORTED |
| Screenshot archive via in-app browser | Current captures are transient; the in-app browser exposes no supported workspace-save operation for screenshot bytes. | UNSUPPORTED (archive mechanism only) |
| Approved-reference visual comparison | Only bounded live screenshots were visually inspected; the required same-state comparison across every page/reference and all four viewports remains undone. | VERIFICATION GAP |

The complete goal remains open. A later full-image build succeeded, so the
earlier build failure is historical and resolved. The fresh owner-authorized
measurement-persistence replay remains a verification gap only; prior real
measurement/reload/restart/export evidence remains PASS. Screenshot/reference
comparison, remaining accessibility/E2E/security gates, live visual verification
of the updated geometric brand mark, and the unsupported cases below are not
represented as completed.

## Real Task and artifact identity

All viewer checks used this existing native WebODM identity; the real Project,
Task, and output artifacts were not deleted or rewritten:

- Project: `2`
- Task: `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6`
- Task name: `Morris Thomas Road - 01/08/2016`
- Task status: `40` (completed), `partial=False`
- Dataset CRS: EPSG `32615` (WGS 84 / UTM zone 15N)
- Artifact revision: `043f46bc045268ec9fffc375a46bf3f846817a44b097336b4ffa809250e216b7`
- `available_assets`: `all.zip`, `orthophoto.tif`, `georeferenced_model.laz`, `textured_model.zip`, `textured_model.glb`, `dsm.tif`, `cameras.json`, `shots.geojson`, `report.pdf`
- Orthophoto and DSM extents were present in the Task record and the DSM extent was accepted by the volume API.

The artifact revision displayed by the browser is the short prefix
`043f46bc0452`; the server-side record above is the full hash.

## Viewer and measurement gate

| Requirement | Concrete action/evidence | Status |
| --- | --- | --- |
| MapView real rendering | Opened `/astrakriti/runs/e99b8afd-ab89-4a4b-9d63-2544ca3a18d6/map/`. The native WebODM map showed the Task heading, visible orthophoto pixels, Layers/Base Maps/Measure controls, CRS `WGS 84 / UTM zone 15N`, `DSM volume: AVAILABLE`, and the artifact revision. | PASS |
| Map layers | Expanded Layers; Orthophoto reported GeoTIFF RGB, min/max `0/255`, EPSG:32615. Surface Model reported min/max `371.544/390.300`, Viridis coloring, Normal shading, EPSG:32615. Orthophoto was toggled off and the colored DSM raster remained visible. | PASS |
| Map native interactions | Pan/zoom and native measurement control were exercised. Direct map reload after deployment returned the same real Task, layer controls, CRS, DSM availability, and persisted rows. | PASS |
| Potree real rendering | Opened `/astrakriti/runs/e99b8afd-ab89-4a4b-9d63-2544ca3a18d6/model/`. Accessibility state contained `Native Potree 3D viewer`, `potree_render_area` with an image, actual Point/Distance/Area/Volume/Height and clipping tools, and the real Task heading. The screenshot showed rendered point-cloud geometry rather than an empty canvas. | PASS |
| Potree native interaction | Orbit, zoom, full extent, EDL off/on, point picking, and polygon clipping were exercised. Point picking produced real UTM/Z output, including `543384.340 / 5180752.640 / 382.521`. | PASS |
| Native 3D persistence | `Task.potree_scene` was reloaded after browser reload and after `docker compose ... up -d --force-recreate webapp worker`; server-side inspection showed a dictionary with one native Potree measurement. The point label was visible again after reload/restart. | PASS |
| Distance | Native Map measurement saved `Map distance`: `18.99338307861003 m`, LineString, method `WebODM native Leaflet measurement`, EPSG:4326. Independent EPSG:4326 → EPSG:32615 control gave `18.971120066388 m`; delta `0.022263012222 m`, relative `0.117%`, within a declared 1% tolerance. | PASS |
| Area and DSM volume | Native DSM-enabled polygon reported perimeter `49.047 m`, area `102.62 m²`, base method `Triangulate`, and volume `45.2516 m³`. Saved record is type `volume`, method `WebODM DSM volume / triangulate base surface`, EPSG:4326. | PASS |
| Independent DSM control | Independent raster control over the real `dsm.tif` (EPSG:32615) gave area `103.131836 m²` and triangulated volume `45.744096 m³`. Area relative delta was `0.499%`; volume relative delta was `1.088%` (41914 raster pixels), within the declared 2% volume tolerance. | PASS |

The two intended persisted map measurement IDs at the end of the gate were:

- `a451e8d9-72ec-4537-a31c-0628a59d2006` — `Map distance`, result `18.99338307861003 m`.
- `f43c4f93-de32-45b7-9246-44ea14214c7b` — `Acceptance DSM volume`, result `45.2516 m³`.

Both carried the same full source artifact revision as the Task and had
`stale=False` before cleanup.

## Persistence, permissions, and export

| Requirement | Concrete evidence | Status |
| --- | --- | --- |
| Create/rename/delete API | Authorized owner test client: disposable measurement create `201`, rename `200` to `live-delete-probe-renamed`, delete `204`; the response then contained only the two intended records. | PASS |
| Rename persistence | `Map area` was renamed through the task-scoped PATCH endpoint to `Acceptance DSM volume` (`200`), then the browser measurement workspace and map/model lists showed the renamed value after reload. | PASS |
| Browser reload | Map, model, and Measurements deep links were reloaded; stable IDs, geometry, results, methods, CRS, and Task association remained visible. | PASS |
| Server restart/recreate | `docker compose -f docker-compose.yml up -d --force-recreate webapp worker` recreated both application services. Afterward the Task still had the Potree scene measurement and the two map records; a fresh map/model load displayed them. | PASS |
| Public read-only policy | Server snapshot: Project `public=False`, `public_edit=False`; Task `public=True`, `public_edit=False`. Owner project permissions were `change_project/delete_project/view_project`; viewer had `view_project` only. | PASS |
| Unauthorized writes | Earlier live probes against the real Task returned viewer `POST/PATCH/DELETE = 404` and anonymous `POST = 403`; owner write succeeded. The viewer UI rendered `READ-ONLY — change permission is required to edit or delete.` after the permission-shell fix. | PASS |
| Authorized export | Owner `GET /api/plugins/astrakriti3d/measurements/task/<task>/export/?format=geojson` with JSON Accept returned `200`, `Content-Type: application/geo+json`, and 2 features. Top-level feature IDs exactly matched the two stable DB IDs; LineString/Polygon vertices and properties matched the persisted records, including Task ID, Project ID, units, CRS, method, result, and artifact revision. | PASS |
| Viewer download event | Clicking the browser Export GeoJSON link did not expose a Playwright/IAB download event during this run; the URL stayed on the map page. The server-side parsed export above is valid. | UNSUPPORTED |

The public `GET` and export responses are intentionally `200` because this real
Task is public for read-only sharing. Public edit remained false, and write
denial was verified separately.

## Explicitly unresolved gate items

These were not silently treated as success:

| Item | Status and reason |
| --- | --- |
| Missing DSM, NoData/incomplete coverage, unknown vertical units, changed base surface | Missing DSM is PASS with HTTP `400`; NoData/incomplete coverage is PASS with an explicit error after the focused guard; changed base surfaces are PASS with distinct real outputs for `triangulate`, `plane`, `average`, `highest`, and `lowest`. The real DSM band exposes no vertical-unit metadata (`units=(None,)`), so unknown vertical-unit semantics remain UNSUPPORTED rather than being claimed as verified. |
| Save failure/slow reconnect, concurrent measurement editors, stale response conflict recovery | PASS for browser-injected failed save/retry and two-context stale-editor conflict recovery above. Slow reconnect, navigation during an in-flight save, and polling cleanup under every native viewer transition remain UNSUPPORTED. |
| Task output revision/stale-measurement invalidation | PASS on disposable Project `8` / Task `e58bcf57-bc84-4a81-b1fa-27429832d491`: a copied `report.pdf` artifact produced revision `eba9c9920194…`; after changing only that disposable file’s mtime, revision became `57e4d27ac56d…` and the persisted measurement API returned `stale=true`. The disposable project, task, measurement, and user were safely removed. Actual reprocessing, corrupt/expired artifacts, and missing-layer preservation remain UNSUPPORTED. |
| Private-project denial and explicitly enabled public-edit policy | PASS on disposable Project `7`: private denial, public read-only denial, and explicitly enabled public-edit writes matched the recorded `404`/`201`/`200`/`204` matrix. The real Project `2` sharing policy was not changed. |
| Companion video/SRT preparation and import | PASS for the configured protected companion boundary above, including real HTTP upload, asynchronous preparation, telemetry association, validated bundle import, and guarded cleanup. The default deployment is restored to `not_configured` after the isolated gate; it correctly disables this optional path until operators provide the documented URL/token. | PASS for configured integration; default deployment remains NOT_CONFIGURED |
| Full browser E2E, New Reconstruction browser submission, responsive matrix, and complete error-path matrix | Exact viewport route coverage, real browser file selection, native intake/cancel, first-use create, search/sort, back/forward/deep-link, reduced-motion, and the exercised console/network checks are PASS above. Full empty-state copy coverage, visual-reference comparison, and the complete failure/race matrix remain UNSUPPORTED. |
| Browser-native UI delete click | PASS. The real Measurements workspace confirmation was accepted and the row disappeared; the task-scoped GET returned an empty list. |

Because the unresolved items above are required by the full goal document, this
live viewer/measurement milestone is evidenced but the overall goal must remain
open. No completion claim is made.

## Page-area status for the larger goal

This focused resumed run did not re-run the full page matrix. The statuses
below prevent the live viewer PASS from being mistaken for full product
completion:

| Retained area | Status in this run |
| --- | --- |
| Overview / Dashboard | PASS for live route/shell/data rendering at the available 1280-wide viewport; full first-use and lifecycle E2E UNSUPPORTED |
| Missions | PASS for live route, real rows, search, and sort at the available viewport; full create/filter/back matrix UNSUPPORTED |
| Mission Overview | PASS for live project route, context navigation, and real linked runs; full lifecycle E2E UNSUPPORTED |
| Run Overview | PASS for the real Task route and live Task identity/status; full polling/recovery E2E UNSUPPORTED |
| New Reconstruction | PASS for labelled form, empty validation, real Playwright file selection, supported native still intake/commit, cancellation, and the protected companion preparation/import API; full page lifecycle/error E2E remains UNSUPPORTED |
| Processing / Recovery | PASS for live route, real run links, honest no-context handling, and disposable native cancellation; retry/recovery browser flows beyond cancellation UNSUPPORTED |
| Frame Review | PASS for live route with 5 real frame images and accessible link names; full review/action matrix UNSUPPORTED |
| Telemetry Review | PASS for the protected preparation/import contract; page E2E UNSUPPORTED |
| Map Workspace | PASS for the real completed Task, before cleanup |
| 3D Model Workspace | PASS for the real completed Task, before cleanup |
| Validation / Evidence | PASS for live route and honest validation/evidence state at the available viewport; full evidence mutation/recovery E2E UNSUPPORTED |
| Reports / Exports | PASS for live route, real artifact list, and authenticated artifact downloads; browser download-event capture UNSUPPORTED |
| Settings / System Health | PASS for live route, connection badges, storage values, and refresh; configuration mutation and failure matrix UNSUPPORTED |
| Measurements workspace | PASS for create/rename/delete UI and API, save retry, stale-editor conflict recovery, reload/restart/permission/API export, before cleanup |

## Final diff review

The final review found no temporary Dockerfile, temporary compose override,
temporary debug print, or
`captureOnCommitCallbacks` compatibility code. The two focused JavaScript
syntax checks, the focused DSM coverage regression, the optimistic measurement
conflict regression, and `git diff --check` pass, and no dependency or
unrelated framework change was added. The focused native WebODM changes in
this resumed gate are the NoData/incomplete-coverage guard in
`coreplugins/measure/volume.py`, request-owned companion-upload staging and
stale-editor conflict handling in `coreplugins/astrakriti3d/api.py`, the
corresponding visible measurement action status in `shell.js`, and the
reduced-motion media rule in `astrakriti.css`; each new behavior is covered by
the targeted test or live browser evidence above. Existing user working-tree implementation files
and untracked project files were preserved; the acceptance changes are limited
to the Astrakriti3D permission/transaction behavior, measurement/export/viewer
integration already under test, and this evidence documentation. No real
Project 2, Task, source media, or reconstruction artifact was deleted or
mutated by cleanup.

## Cleanup performed

Only resources created by this acceptance run were cleaned. The real Project,
Task, source media, and reconstruction artifacts were preserved. Disposable
measurement probes were removed through the task-scoped API/DB path, including
probe ID `ee0a10b3-05c6-49c7-86d5-9b31ba0977b6` and live-delete probe ID
`010c1b16-b41a-4666-9060-54ddef070ec7`. After the evidence was written, the
two intended measurement IDs listed above were removed, `Task.potree_scene`
was restored to `{}`, empty acceptance Projects `3` and `4` were removed, and
the two earlier acceptance-only user accounts were removed. The resumed
browser audit created user `audit_owner_2026`; WebODM automatically created
Project `5` (`First Project`) for that user. Inspection confirmed Project `5`
had zero Tasks and was created at the audit login time, so only that disposable
Project and user were removed. Final cleanup verification returned
`audit_user_after=False`, `project5_after=False`, `real_task_exists=True`, and
`real_project_exists=True`. The resumed native-intake check also created user
`e2e_owner_2026`, Project `6`, Task
`235f182b-8d31-43a0-a72c-dfcbbfce633c`, and submission
`6ea355da-f245-4980-ab5b-38a5b20655c4`. The Task was canceled, then WebODM’s
safe project deletion completed; the exact orphaned submission row was removed
afterward, followed by the temporary user. Final verification returned
`user_exists=False`, `submission_exists=False`, `project6_after=False`,
`task_after=False`, `real_task_exists=True`, and `real_project_exists=True`.
The permission-matrix check also created owner/viewer users
`perm_owner_2026`/`perm_viewer_2026`, Project `7`, Task
`0c887e5c-ad2a-4639-9af1-f451d4e06ba7`, and a disposable measurement. The
measurement was deleted, WebODM project deletion was allowed to finish after
the zero-file partial Task was released to the normal REMOVE worker path, and
both users were then removed. Final verification returned
`owner_after=False`, `viewer_after=False`, `project7_after=False`,
`task7_after=False`, and `measurement_after=False`.
The output-revision check created user `revision_owner_2026`, Project `8`,
Task `e58bcf57-bc84-4a81-b1fa-27429832d491`, and measurement
`3cb00419-7dea-48f4-824c-42adeb214d89`; WebODM deletion completed before the
user was removed. Final verification returned `user_after=False`,
`project8_after=False`, `task8_after=False`, and `measurement_after=False`.
The concurrent reservation check created user `race_owner_2026`, Project `10`,
Task `d390d9b3-a3dc-439f-b319-20e2428248d0`, and submission
`efff12ac-a2a7-4ccd-8901-442a176693e8`; cleanup verification returned
`user_after=False`, `project10_after=False`, `task10_after=False`, and
`submission_after=False`. The protected companion gate then created user
`companion_http_gate_20260919`, Project `13`, Task
`b30fbb92-1e7f-476f-8664-a061b88a87f2`, and submission
`d2c464d4-b0f7-497c-a6ea-7b0b76fa63ab`; WebODM native project deletion and
the exact partial-task release completed before the temporary user,
submission, and companion runtime root were removed. Final verification
returned no Project `13`, Task, submission, or temporary user, and the normal
compose deployment was restored with no companion environment variables.
The temporary Playwright browser gate then created user
`playwright_gate_20260919`, Project `14`, Task
`cfb11d36-6860-46ac-9eaf-d666a4c83a0a`, and submission
`a134e85b-8a26-4454-8915-b9472b31b1e0`; the Task was canceled at status `50`,
then native project deletion completed. Final verification returned no Project
`14`, Task, submission, or temporary user, and the temporary Playwright
package, screenshots, and runner were removed.
The resumed measurement reliability gate used disposable user
`save_gate_20260919` against the preserved Project `2` / Task
`e99b8afd-ab89-4a4b-9d63-2544ca3a18d6`. It created and removed the browser
delete/save-retry/conflict measurements through task-scoped endpoints; the
final database check returned zero Astrakriti measurements for the real Task.
The temporary `qa/live_save_gate.cjs` and `qa/live_conflict_gate.cjs` files
were removed after the evidence was recorded. The Playwright package remains
outside the repository under the task-specific `%TEMP%` directory so a later
browser gate can be repeated without adding a project dependency.
The first-use/context gate then created user `first_use_gate_20260919`,
Project `15`, Task `7ce8ff32-27ca-4493-9867-6ac2b4e5021f`, and submission
`a5af6b22-134e-4b8d-b0a8-c91b66ff7720`; the Task was canceled, native Project
deletion returned `204` and completed asynchronously, and the orphaned
submission row was removed only after Project deletion completed. Final guarded
verification returned no Project `15`, Task, submission, or temporary user.

## Windows-compatible image build and fresh restart verification — 2026-09-19

This continuation resumed the live gate after Docker Desktop became healthy.
The initial standard image build exposed a Windows checkout line-ending issue:
the root `Dockerfile` heredoc reached `apt-get` with a trailing carriage return,
and direct execution of `nodeodm/setup.sh` failed on its CRLF shebang. The
root `.gitattributes` now pins `Dockerfile*` and `*.sh` to LF; the tracked
Dockerfiles and shell scripts were normalized to LF without changing their
Git blob contents. The normal build then completed successfully.

| Requirement | Concrete action/evidence | Status |
| --- | --- | --- |
| Standard Docker image build | `docker compose -f docker-compose.yml -f docker-compose.build.yml build webapp` exited `0`; `webodm/webodm_webapp:latest` resolved to image `sha256:99e015c13a174121591d8554df0e163cbe74819f339dce5f5b7a15c8ce3ab3d3`. The previously running image remains locally tagged `migration-index-alignment-20260919` for rollback. | PASS |
| Migration state on built image | `docker exec webapp python manage.py showmigrations app` listed `0053_astrakriti_measurement` through `0056_astrakriti_legacy_link` as `[X]`; there were no unapplied app migrations. | PASS |
| Model/migration consistency | Built-image `manage.py makemigrations --check --dry-run` returned `No changes detected`. | PASS |
| Django system check | Built-image `manage.py check` returned `System check identified no issues (0 silenced)`. | PASS |
| Focused backend tests | `docker compose -f docker-compose.yml -f docker-compose.build.yml run --rm --no-deps --entrypoint python webapp manage.py test app.tests.test_astrakriti3d --verbosity 2` returned `Ran 13 tests in 3.705s` / `OK`; test database was destroyed afterward. | PASS |
| Application restart | `docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --no-deps webapp worker` recreated and started only `webapp` and `worker`; both now run image `sha256:99e015c13a174121591d8554df0e163cbe74819f339dce5f5b7a15c8ce3ab3d3`. `db`, `broker`, and `node-odx-1` were not recreated. | PASS |
| Real WebODM Task after restart | Read-only Django query returned Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6`, Project `2`, status `40`, `partial=False`; public fields remained Project `public=False/public_edit=False` and Task `public=True/public_edit=False`. | PASS |
| MapView after restart/reload | Reloaded `/public/task/e99b8afd-ab89-4a4b-9d63-2544ca3a18d6/map/`; real orthophoto pixels rendered, task heading and native Layers/Base Maps/Measure/3D controls were present, and browser error/warning log was empty. Opened the measurement panel; it showed `Measure volume, area and length`. | PASS |
| Potree after restart | Opened the same Task's `/3d/` route; `#potree_render_area` and three canvases were present, the real point cloud visibly rendered, and Point/Distance/Area/Volume/Height and clipping controls were exposed. Browser error/warning log was empty. | PASS |
| Fresh map-measurement persistence replay | The guarded post-restart query returned `map_measurements=0`, matching the earlier deliberate cleanup. Earlier owner-session evidence already proves saved measurements survived reload and service recreation and were parsed from GeoJSON. This turn did not repeat that sequence on the accepted Task. | VERIFICATION GAP (fresh replay only; earlier persistence/export evidence remains PASS) |
| Current GeoJSON endpoint | Public read-only GET to `/api/plugins/astrakriti3d/measurements/task/e99b8afd-ab89-4a4b-9d63-2544ca3a18d6/export/?format=geojson` with `Accept: application/json` returned HTTP `200`, `Content-Type: application/geo+json`, `FeatureCollection`, zero features. This is consistent with the zero-row database. | PASS (empty export only) |
| Empty MapView export state | With zero current rows, `Export Measurements` was disabled; this is the truthful empty state. The earlier non-empty owner-session export returned two parsed GeoJSON features matching the persisted records. | PASS (empty state and prior non-empty server export) |
| Browser-native download event | A browser download event was not observed during the prior click attempt. The server-side non-empty GeoJSON response and parsed geometry are independently PASS; this row makes no claim that export itself is broken. | VERIFICATION GAP (browser event only) |
| Non-empty export and measured values | The earlier owner-authorized live acceptance evidence above remains: the real distance (`18.99338307861003 m`), area (`102.62 m²`), and DSM volume (`45.2516 m³`) matched independent controls within the recorded tolerances; both saved IDs survived reload/restart before deliberate cleanup. The earlier authorized GeoJSON export parsed as 2 features with matching IDs/geometry/properties. | PASS (historical live evidence; rows intentionally cleaned) |
| Permission matrix | The live database still reports the real Project private and the Task public but not publicly editable. The earlier owner/viewer permission matrix and unauthorized-write denials passed; no permission changes or fresh replay were needed for this continuation. | PASS (prior full matrix and current policy state) |

Build warnings were non-fatal and were not “fixed” with speculative upgrades:
Webpack emitted bundle-size/deprecation warnings, npm reported 95 dependency
vulnerability findings (55 moderate, 22 high, 18 critical), and pip reported
an existing `wheel`/`packaging` version conflict. Dependency versions were
left unchanged.

This continuation strengthened the migration/build/restart and real viewer
evidence, but did not close the larger goal. The deliberate absence of current
measurement rows is not a product failure: the earlier non-empty save,
reload, service-recreation, permission, and parsed-export evidence remains
PASS. A fresh replay is a verification gap only and is not being repeated on
the accepted Task. Full route/viewport/accessibility/visual-reference and
remaining E2E matrices listed above are still unresolved. No completion claim
is made.

## Current runtime/source reconciliation — 2026-09-19 17:34–17:37 Asia/Calcutta

Read-only continuation check from the current WebODM worktree. It did not
restart services, run migrations, alter Project/Task state, change permissions,
or create measurement rows.

| Check | Evidence | Status |
| --- | --- | --- |
| Running services and image | `docker info` reported server `29.8.0`, 5 running containers, `overlayfs`. Compose showed `webapp`, `worker`, `db`, `broker`, and `node-odx-1` up. `webapp`/`worker` still use image `sha256:99e015c13a174121591d8554df0e163cbe74819f339dce5f5b7a15c8ce3ab3d3`, created `2026-09-19T08:43:38Z`. | PASS (runtime healthy; image predates current source) |
| Deployed migration inventory | At this historical checkpoint the running image listed `0053`–`0056`; later controlled deployment of `sha256:6743daa6…` applied and verified migrations `0053`–`0057`. The newly rebuilt image was separately checked against that database on 2026-09-20. | PASS (later deployed/runtime and built-image checks) |
| Live database migration/table | Read-only PostgreSQL query as the container's `postgres` OS user returned `0057_astrakriti_mission_metadata` and `app_astrakritimissionmetadata`. | PASS (schema migration is present in DB) |
| Standard image build, attempt 1 | Cached dependency stages and Webpack completed; `python manage.py translate build --safe` exited `139` with `Segmentation fault` before FFmpeg. | FAIL (transient build failure) |
| Translation isolation | Disposable `docker compose run --rm --no-deps --entrypoint python webapp manage.py translate build --safe` against the deployed image exited `0`. This changed no persistent database/media state. | PASS (isolated command) |
| Standard image build, attempt 2 | Webpack, collectstatic, plugin rebuild, and translation compilation completed, but the pinned FFmpeg transfer was interrupted after a partial first attempt. A later complete standard build and verification are recorded in the 2026-09-20 section below; no alternate/unpinned FFmpeg was substituted. | PASS (historical transfer interruption later resolved) |
| Running service/data safety | Both build attempts only built images; neither recreated `webapp`/`worker` nor ran `start.sh`. The accepted real Project/Task and its sharing policy were not modified. | PASS |

At this 2026-09-19 checkpoint, the running image predated migration `0057` and
the standard build was interrupted during the pinned FFmpeg download. Both
conditions were later resolved: the 2026-09-20 runtime ran image
`sha256:6743daa6…` with migrations `0053`–`0057` applied, and the standard
full-image build completed as `sha256:de81b875…`. That newly built image passed
isolated Django/migration checks but was not deployed; the running services
remain on the previously verified `6743daa6…` image. Do not run `start.sh` as a
casual workaround: this repository's startup path runs `unlock_all_tasks.py`.

## Current-source build and controlled deployment — 2026-09-19 18:08–18:17 Asia/Calcutta

The following supersedes the older-image state above. The pinned FFmpeg URL and
version were not changed. The installer now fetches 1 MiB HTTP byte ranges,
checks each `Content-Range`, resumes interrupted transfers, tolerates servers
that ignore Range by restarting the file, validates ZIP CRCs, and extracts only
the expected root `ffmpeg` member.

| Check | Evidence | Status |
| --- | --- | --- |
| Range endpoint behavior | Read-only request for bytes `0-0` returned HTTP 206, `Content-Range: bytes 0-0/29753452`; a 1 MiB request returned HTTP 206 with all `1,048,576` requested bytes in `21.92s`. | PASS |
| Installer regression tests | `python -c "import sys,unittest; sys.path.insert(0,'.'); import app.tests.test_install_ffmpeg as t; unittest.main(module=t,verbosity=2)"` ran 2 tests: interrupted transfer resumes at the exact next byte, and a server ignoring Range replaces rather than appends. Both passed. | PASS |
| Standard source image build | `docker compose -f docker-compose.yml -f docker-compose.build.yml build webapp` exited `0`; pinned FFmpeg 7.0.2 archive completed, ZIP validated, and image built as `sha256:b8bbe0cd9333651cc0e532e765c16621c6903d7106ee15c4a4d9f2a304f65df0`. | PASS |
| Current-source plugin tests | Initial run found `NameError: quote is not defined` in the frame-review path. Added the missing `urllib.parse.quote` import. Re-run `manage.py test app.tests.test_astrakriti3d app.tests.test_install_ffmpeg --verbosity 1`: `Ran 21 tests in 29.258s — OK`. | PASS after focused fix |
| Model and migration state | On the built image, `manage.py check` reported no issues, `makemigrations --check --dry-run` reported `No changes detected`, and `showmigrations app` showed `0053` through `0057` applied. | PASS |
| Pre-restart task guard | Read-only `get_pending_tasks()` query returned `[]`; accepted Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6` was status `40` with no pending action. | PASS |
| Controlled service deployment | `docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --no-deps webapp worker` recreated only those two services. Both now use image `sha256:b8bbe0cd9333651cc0e532e765c16621c6903d7106ee15c4a4d9f2a304f65df0`; database, broker, NodeODM, and media volume were not recreated. `GET /login/` returned HTTP 200. | PASS |
| Post-deploy task state | Status counts were `30:1`, `40:2`, `50:2`; accepted Task remained status `40`, `partial=False`. The Project/Task permissions were not changed. | PASS |
| Mission metadata GET behavior | Read-only `MissionMetadataView` GET using the existing Project 2 owner returned HTTP 200, `project_id=2`, `recorded=False`; metadata row count stayed `0 → 0`. This directly invokes the current view and does not write Project or Task data. | PASS |

The custom image is now built and running with current migrations/API code. This
does not complete the overall goal: the standard video companion remains
unconfigured in normal Compose, and the remaining page workflow, accessibility,
visual-reference, and full browser E2E gates remain outstanding. The real
measurement rows remain intentionally cleaned; prior real measurement,
reload/restart, permission, and parsed-export evidence remains valid.

## Opt-in preparation companion deployment — 2026-09-19 18:29–18:30 Asia/Calcutta

An ephemeral 256-bit token was generated in the deployment shell and passed
only as a Compose environment variable. It was not written to source or printed.
The companion is internal-only; its Compose service exposes port 5001 to the
Compose network but publishes no host port.

| Check | Evidence | Status |
| --- | --- | --- |
| Companion image build | `docker compose -f docker-compose.yml -f docker-compose.astrakriti.yml build astrakriti-companion` completed; image manifest `sha256:ab01b24d2af26685a8c1533cce06b499cee165a1993d586561f556744725c7e4`. Image runs as UID 10001 and includes ffmpeg/ffprobe. | PASS |
| Startup and steady state | Compose `ps astrakriti-companion webapp` showed both `Up`; companion displayed container-only `5001/tcp`, with no host binding. | PASS |
| Authentication | In-container Flask health probe without a bearer token returned HTTP 401; probe using the container-held bearer token returned HTTP 200. The token value was not emitted. | PASS |
| WebODM service connectivity | `docker exec webapp python manage.py shell -c "from coreplugins.astrakriti3d.companion import AstrakritiCompanionClient; print(AstrakritiCompanionClient(timeout=5).health_payload())"` returned `{'status': 'connected', 'detail': 'Protected Astrakriti preparation service is ready.'}`. | PASS |
| Companion API regression tests | `python -m pytest -q tests/test_companion_api.py` returned `3 passed in 0.45s`. | PASS |
| Isolated video-preparation journey | In the deployed companion image, generated an 8-second synthetic clip and exercised an isolated temporary instance of the production Flask app over HTTP: upload returned `202`, preparation reached `completed`, bundle GET returned `200` (202,030 bytes), manifest contained 8 frames with no missing frame files, and local mode correctly omitted `geo.txt`. Reposting identical source/job identity returned `202` with existing `completed` status. | PASS (synthetic input; no WebODM submission) |
| Isolated test-data cleanup | The test used Python `TemporaryDirectory` beneath the writable temp mount. A follow-up query found no remaining `acceptance-video-*` directory in that mount. | PASS |
| Accepted Task unchanged | Read-only query returned Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6`, status `40`, `partial=False`. No Project/Task permissions or measurements were changed. | PASS |

The companion service is now configured in the running opt-in Compose stack.
The HTTP preparation/bundle contract has been exercised with synthetic media,
but not through WebODM's New Reconstruction UI or with real capture media;
Task creation/submission remains untested here. Full browser E2E/page,
accessibility, and visual gates remain outstanding. The previous measurement
replay remains a verification gap, not evidence of a broken implementation.

## Isolated WebODM-to-companion API integration — 2026-09-19 18:55–19:07 Asia/Calcutta

This gate used the current WebODM application image plus the checked-out test
module copied into a disposable runner, a fresh Django test database, and a
separate temporary companion container on the private Compose network. The
test bearer token was generated for this run and not printed or persisted. A
synthetic 8-second georeferenced video with timestamp-matched SRT was used; no
application Project 2 or accepted real Task was accessed. Invocation (token
redacted):
`docker exec -e ASTRAKRITI_COMPANION_TEST_ISOLATED=1 -e ASTRAKRITI_COMPANION_URL=http://astrakriti3d-companion-acceptance:5001 -e ASTRAKRITI_COMPANION_TOKEN=<ephemeral> astrakriti3d-webapp-acceptance python manage.py test app.tests.test_astrakriti3d.TestAstrakriti3D.test_live_companion_video_to_native_intake --verbosity 1`.
The worker enqueue was mocked at commit so no reconstruction was run.

| Check | Evidence | Status |
| --- | --- | --- |
| Test schema and app checks | `manage.py test app.tests.test_astrakriti3d.TestAstrakriti3D.test_live_companion_video_to_native_intake --verbosity 1` created a disposable test database, applied migrations through `0057`, and reported `System check identified no issues (0 silenced)`. | PASS |
| Native intake through real companion HTTP | `TestAstrakriti3D.test_live_companion_video_to_native_intake` ran with `ASTRAKRITI_COMPANION_TEST_ISOLATED=1` and a unique token on a disposable companion container. It reserved a native Project/partial Task in the test DB, POSTed an 8-second synthetic video plus 8 timestamp-matched SRT records through `IntakePreparationView`, polled to `completed`, and imported through `IntakePreparationImportView`. It verified 8 task images, 8 frame-review records, 8 matched telemetry records, and an EPSG:4326 `geo.txt` with header plus 8 image-coordinate rows. | PASS |
| Commit and idempotency | The test committed the imported Task, repeated import and commit, observed the reuse responses, verified processing enqueue was invoked exactly once, and verified the Task was no longer partial. | PASS (processing intentionally mocked) |
| Test isolation guard | The live integration test skips unless the disposable-companion opt-in flag, URL, and token are all explicitly set; normal test runs cannot send test jobs to the configured production companion by default. | PASS |
| Default configured-stack safety | In a disposable runner with the ordinary Compose companion URL/token configured but without `ASTRAKRITI_COMPANION_TEST_ISOLATED`, the targeted command completed `OK (skipped=1)`; the test method did not run and sent no request to the persistent companion. | PASS |
| Cleanup and accepted Task safety | Django reported `Destroying test database`; media lived under a `TemporaryDirectory`; temporary runner and tmpfs companion containers were removed. The accepted Task remained status `40`, `partial=False`; the five normal WebODM services remained up. | PASS |
| Browser-driven intake and actual reconstruction | This historical entry predates the disposable browser reconstruction recorded below: Project 17's Task reached WebODM status 40 with real outputs; the 2026-09-20 Project 24 run later verified saved frame selection through completed reconstruction and reload. | PASS (later disposable runs close this gap) |

## Disposable native WebODM reconstruction run — 2026-09-19 20:01 Asia/Calcutta

This live run closed the processing gap using only copies of the five source
images from accepted Project `2` / Task
`e99b8afd-ab89-4a4b-9d63-2544ca3a18d6`. The source Task and image files were
read-only; no sharing or permissions were changed. A single uniquely named
Project was created through the Astrakriti native intake API, verified private
(`public=false`, `public_edit=false`), processed by the actual Celery worker and
NodeODM service, then removed using WebODM's task-removal and project-deletion
paths. The request was made through an authenticated Django client as the
existing superuser; no browser or credentials were used.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Pre-run queue guard | `worker.tasks.get_pending_tasks()` returned `[]`; queued/running Task count was `0`; NodeODM `node-odx-1` queue count was `0`. | PASS |
| Native reservation and safe Project state | `/api/plugins/astrakriti3d/intake/reserve/` returned `201`, Project `17`, Task `24fcb647-59f1-4792-bf06-058b4ddc72cc`, submission `51ff76b7-7960-4a68-8948-8af54250c066`. Project name was `ASTRAKRITI3D-EPHEMERAL-ACCEPTANCE-99c87f54`; both public flags were false. | PASS |
| Native input upload | `/api/projects/17/tasks/24fcb647-59f1-4792-bf06-058b4ddc72cc/upload/` returned `200`; five source JPEGs were copied through the regular WebODM upload endpoint. Their byte sizes and SHA-256 hashes were captured before upload. | PASS |
| Native commit and idempotency | Astrakriti commit returned `200`, `success=true`, `reused=false`; immediate retry returned `200`, `reused=true`, the same Project/Task identity. `partial` changed to false and the worker enqueue happened once. | PASS |
| Real worker and NodeODM processing | Worker log recorded automatic assignment to `node-odx-1` and `Processing…`. The Task progressed from status `20` at `35.4%` to status `40` at `100%` in about 135 seconds, with no `last_error`; status `40` is WebODM `COMPLETED`. | PASS |
| Real output inventory | `available_assets` contained `all.zip`, `orthophoto.tif`, `georeferenced_model.laz`, `textured_model.zip`, `textured_model.glb`, `cameras.json`, `shots.geojson`, and `report.pdf`. `get_map_items()` exposed orthophoto and plant layers; this five-image result had no DSM. | PASS (DSM not supplied by this run) |
| Output delivery | Authenticated GETs returned `200`: orthophoto TIFF 5,521,820 bytes; georeferenced LAZ 2,843,042 bytes; PDF report 5,994,054 bytes; shots GeoJSON 2,354 bytes. | PASS |
| Product route availability | Authenticated Django client GETs to this run's Overview, Map, Model, Measurements, and Reports routes each returned `200`. This checks route access, not client-side viewer rendering. | PASS (route-level only) |
| Guarded cleanup | Native Task `remove` returned `200`; worker removed the Task and Task media. Native Project DELETE returned `204`; Project `17` and its media directory were removed. Because WebODM sets submission Project/Task foreign keys to `NULL` on deletion, the exact test-created orphan submission (`51ff76b7-7960-4a68-8948-8af54250c066`, marker-matched, both links null) was then deleted by an exact guarded ORM filter. | PASS |
| Post-cleanup integrity | Project, Task, submission, and `project/17` media directory all absent; all five source-image SHA-256 values unchanged; accepted Task still Project `2`, status `40`, `partial=false`, with `0` measurement rows; Project `2` remains private/read-only; active Task count, pending worker count, and NodeODM queue all `0`. | PASS |

This proves a new native Task can be committed and reconstructed by the live
WebODM/NodeODM pipeline. It is API-driven acceptance, not a browser-driven
video-to-processing run; the synthetic video/SRT companion integration above
still intentionally mocks processing after import.

## Disposable real-video-to-reconstruction run — 2026-09-19 20:49 Asia/Calcutta

This continuation exercised the production WebODM intake APIs against the
running application database and real Celery/NodeODM worker. The browser
could not open the local WebODM page (`ERR_CONNECTION_REFUSED` in the in-app
browser); per the acceptance instruction not to chase unsupported browser
tooling, no browser submission is claimed. Instead, an isolated companion
container on the private `webodm_default` network used tmpfs for all uploaded
video and preparation outputs. Its token was generated for the run, passed
only in process environment, and not printed or stored. A 5.005-second,
101,026,331-byte stream-copy derivative of the real `DJI_0142.MP4` was paired
with the matching original `DJI_0142.SRT` (1,691,677 bytes). The original
capture files were only read.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Isolated companion | The live companion image ran as a disposable container on `webodm_default`, with a 512 MiB tmpfs owned by UID/GID 10001 and no published host port. WebODM's authenticated companion health client returned `connected`. The persistent companion and its volume were not used for this job. | PASS |
| Native reservation | `/api/plugins/astrakriti3d/intake/reserve/` returned `201`; private Project `18`, partial Task `3e2291eb-7163-48d6-bd0b-0d80a3993cdb`, and submission `185dae67-0555-4076-9cb2-e6f306c3cb21` were created with a unique idempotency key. Both Project sharing flags were false. | PASS |
| Video/SRT preparation | Native `prepare/` returned `202`; status advanced `running → completed` in about 6 seconds using the real protected companion HTTP service. | PASS |
| Import and evidence | Native `import/` returned `200`, `imported=true`, `frame_count=5`; five JPEGs and `geo.txt` were written into the reserved Task. Frame-review returned `available` with 5 frames. Telemetry review returned `available`; all 5 frame associations matched, and `geo.txt` had 6 lines (header + five images). Companion metadata reported 5,801 valid SRT records and zero invalid/parser-error records. | PASS |
| Commit/idempotency | First native commit returned `200`, `reused=false`; immediate retry returned `200`, `reused=true`, same Project/Task. | PASS |
| Actual processing | The normal Celery worker assigned the Task to NodeODM. It progressed at status `20` and reached status `40` / 100%, `last_error=None`. `available_assets` contained `all.zip`, `orthophoto.tif`, `georeferenced_model.laz`, `textured_model.zip`, `textured_model.glb`, `cameras.json`, `shots.geojson`, and `report.pdf`. | PASS |
| Cleanup | WebODM Task remove returned `200`; Project deletion returned `204`. The exact test-created orphan submission was removed after both foreign keys became null. Final queries found no Project 18, Task, submission, pending job, or queued/running Task. The isolated companion container and WebODM staging copy were removed; its tmpfs disappeared with the container. | PASS (application and container cleanup) |
| Protected data integrity | Project 2 stayed private (`public=false`, `public_edit=false`); accepted Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6` stayed in Project 2, status `40`, non-partial, public read-only (`public=true`, `public_edit=false`), with zero measurement rows. No permissions or measurements were changed. The original video/SRT size and modification-time values remained unchanged. | PASS |
| Host temporary derivative cleanup | At this checkpoint, the generated 101,026,331-byte clip and 1,691,677-byte SRT remained in the named task-specific temp directory. On 2026-09-20, read-only inventory found exactly those two files at the recorded sizes; both and the now-empty directory were then removed and absence verified. | PASS (cleanup completed later) |
| Browser-driven video intake | This historical run used native APIs because the browser endpoint was unavailable then. Later authenticated Docker-origin disposable browser runs verified file selection, video/SRT preparation, candidate review, submission, and completion of a native Task. | PASS (later browser evidence supersedes this checkpoint) |

This run closed the real-media companion-import-to-native-processing gap at
the API/service boundary. Its contemporaneous note that browser-driven
submission was unproven was superseded by later authenticated disposable
browser runs. The full accessibility, error/race, visual-reference, and
remaining browser E2E checks are still separate.

## Durable frame-selection acceptance — 2026-09-19 21:55 Asia/Calcutta

The New Reconstruction workflow now requires an explicit candidate-frame
review before commit. This continuation built the current workspace source
and, after a read-only check confirmed there were no queued/running Tasks,
recreated only the `webapp` and `worker` services. The accepted Project 2/Task
was not modified, permissions were not changed, and no measurement data was
created.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Current-source image build | `docker compose -f docker-compose.yml -f docker-compose.build.yml build webapp` completed, including WebODM/plugin rebuild and pinned FFmpeg 7.0.2 validation. New manifest: `sha256:0e2cda362040615685962cc4f20e4ea375a3c1f6b7645026f5f26f61c9091434`. | PASS |
| Isolated current-source selection tests | `docker compose -f docker-compose.yml -f docker-compose.build.yml run --rm --no-deps --entrypoint python webapp manage.py test` with the three `test_frame_selection_*` methods returned `Ran 3 tests in 2.270s — OK`; Django system checks were clean. The disposable test database was destroyed afterward. | PASS |
| Selection persistence and commit retry | `test_frame_selection_is_persisted_applied_and_commit_retry_is_safe` verified persisted manual selection, exclusion archive/hash behavior, selected Task-root images, count, and one worker enqueue across commit retry. | PASS |
| Georeferenced parity | `test_georeferenced_selection_keeps_source_geo_and_filters_authoritative_geo` verified immutable source `geo.txt` preservation and authoritative EPSG:4326 filtering to the selected image identities. | PASS |
| Stale inputs and authorization | `test_frame_selection_rejects_stale_images_and_other_owners` verified stale candidate rejection and foreign-owner denial. | PASS |
| Reload behavior in code | This earlier static-only checkpoint was superseded by the 2026-09-20 Project 24 browser run: the saved 50-frame selection was read back from server metadata, and the completed Run route retained Frames=50 after reload. | PASS (later disposable browser verification) |
| Live service deployment preflight | Running `webapp` and `worker` were on image `sha256:b8bbe0cd9333651cc0e532e765c16621c6903d7106ee15c4a4d9f2a304f65df0`. Correct status-code lookup showed counts `FAILED=1`, `COMPLETED=2`, `CANCELED=2`; there were `0` queued Tasks, `0` running Tasks, `0` pending actions, and `worker.tasks.get_pending_tasks()` returned `[]`. The sole status-30 Task is FAILED, not processing. | PASS (safe deploy gate clear) |
| Controlled source deployment | Carried forward the running container's companion token without printing it and ran `docker compose -f docker-compose.yml -f docker-compose.build.yml -f docker-compose.astrakriti.yml up -d --no-deps webapp worker`. Both app services now use `sha256:0e2cda362040615685962cc4f20e4ea375a3c1f6b7645026f5f26f61c9091434`; database, broker, NodeODM, companion container, and media volume were not recreated. | PASS |
| Post-deploy startup and app health | Plugin startup registered `coreplugins.astrakriti3d.plugin`; `docker exec webapp python manage.py check` reported no issues; `/login/` returned HTTP 200. Migrations `0053`–`0057` were all applied. | PASS |
| Live selection route and authorization | Django URL resolution identified the plugin API handler for `/api/plugins/astrakriti3d/intake/<submission>/selection/`; an unauthenticated GET returned HTTP 403. Authenticated selection behavior is covered by the three isolated source-image tests above; no accepted Task was used. | PASS (route registration and unauthenticated denial) |
| Companion connectivity | Post-deploy `AstrakritiCompanionClient(timeout=5).health_payload()` returned `{'status': 'connected', 'detail': 'Protected Astrakriti preparation service is ready.'}`. | PASS |
| Protected Task post-deploy guard | Read-only query returned accepted Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6`: status `40`, `partial=False`, Project `2` with `public=False`, `public_edit=False`, measurement count `0`. Queued/running/pending counts remained `0`. | PASS |
| Accepted data and service integrity | No Project/Task mutations, permission changes, or measurement writes were performed. `db`, broker, NodeODM, companion container, and persistent media volume were not recreated. | PASS |

The feature is built, deployed, and covered by isolated current-source tests;
live route registration, denial without authentication, startup, and companion
connectivity pass. The browser review/reload/commit interaction remains
unverified because the supported browser session is unavailable. Do not use the
accepted Project/Task for this workflow; browser acceptance requires a
disposable authorized Project/Task and exact-ID cleanup.

## Frame-review cross-page state and engine recovery — 2026-09-19 22:14 Asia/Calcutta

Code review found that navigating between candidate pages could reinitialize
an empty `Set` and overwrite the chosen strategy from the server's original
defaults. `selectionInitialized` now makes the initial saved set/strategy load
exactly once; subsequent page fetches preserve local edits. This keeps fully
unchecked pages unchecked and maintains the `manual` strategy through paging.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| UI source syntax and whitespace | `node --check coreplugins/astrakriti3d/public/shell.js` and `git diff --check` passed after the state fix. | PASS |
| Rebuilt current image | First export attempt lost its Docker RPC connection while Docker Desktop's Linux/WSL engine panicked (`fatal error: fault`); the tag remained at the prior image. No prune/reset was run. After a normal `docker desktop restart`, a cached `docker compose -f docker-compose.yml -f docker-compose.build.yml build webapp` completed successfully. Image manifest: `sha256:305b8aa8b588d8509cab4e6944c17aa7b28b960b1b604aa8225fad94b5a24f21`. | PASS (retry after engine recovery) |
| Source fix in built image | `docker run --rm --entrypoint sh webodm/webodm_webapp:latest -lc "grep ... selectionInitialized ... shell.js"` found the initialization guard in the image. The deployed `/webodm/coreplugins/astrakriti3d/public/shell.js` also contains it. | PASS |
| Controlled deployment | After read-only checks showed `0` queued, `0` running, and `0` pending tasks/actions, recreated only `webapp` and `worker` with the companion overlay and carried-forward token. Both use the new `sha256:305b8aa8…` image. Docker Desktop restart briefly stopped/started the existing stack; no prune, volume removal, database reset, or Task mutation occurred. | PASS |
| Post-deploy route and health | `/login/` returned HTTP 200; URL resolution found the selection API handler; an unauthenticated selection GET returned HTTP 403; the protected companion health API returned `connected`. | PASS |
| Accepted Task and permissions after engine/app restarts | Read-only database query returned Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6` status `40`, non-partial, Project `2` private with `public_edit=False`, and zero measurement rows. Queued/running/pending counts remained zero. | PASS |
| Cross-page interaction itself | At this historical checkpoint, no browser UI interaction had been exercised. Later authorized live tests on disposable Projects 23 and 24 toggled frames on both pages and verified client-side and saved-selection persistence; see the 2026-09-20 sections below. | PASS (historical blocker superseded by later live evidence) |

The Docker export failure was environmental and recovered without destructive
maintenance. The cross-page UI blocker and need for an explicitly permitted
isolated browser dataset were both resolved later by the authenticated
`localhost` browser runs on disposable Projects 23 and 24 below; the accepted
Task was not used for those tests.

## DSM volume-unit qualification and deployment — 2026-09-19 22:49 Asia/Calcutta

The raster-band unit on the accepted DSM is absent, so treating its vertical
values as known metres would overstate the evidence. The calculation now
converts horizontal CRS units and declared vertical band units separately. If
the band unit is absent, it uses the projected CRS unit as an explicit Z-unit
assumption, discloses that assumption and the unknown vertical datum in the
native popup and saved measurement details, and preserves the existing numeric
`output` response field while adding `unit_context`. Unsupported declared Z
units and geographic/non-projected CRSs are rejected.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Focused synthetic regressions | Isolated built-image Django run: `Ran 6 tests in 2.072s — OK`. Tests cover absent Z-unit qualification, horizontal-feet/vertical-metres independent factors, computed volume context, geographic CRS rejection, NoData rejection, and result-endpoint numeric-output/context compatibility. Disposable test DB was destroyed. | PASS |
| Frontend syntax and diff hygiene | `node --check coreplugins/astrakriti3d/public/main.js`; `node --check coreplugins/astrakriti3d/public/shell.js`; `git diff --check`: all passed. Webpack compiled the native measurement popup during the image build. | PASS |
| Source image | `docker compose -f docker-compose.yml -f docker-compose.build.yml build webapp` completed; image digest `sha256:06032151b8922ea50fcc184047396ac0072ad9f623e274817dd3c63c916f60b8`. | PASS |
| Safe deployment preflight | Read-only queries immediately before rollout: queued Tasks `0`, status-20 processing Tasks `0`, worker pending IDs `[]`. The status-30 Task was the previously known failed Task. Accepted Task remained status `40`, non-partial, Project `2` private/read-only, with `0` saved measurement rows. | PASS |
| Controlled deployment | Recreated only `webapp` and `worker` using the current image and the existing companion token carried in-process without printing it. Database, broker, NodeODM, companion, and media volume were not recreated. Both app services report the expected image digest. | PASS |
| Post-deployment health | `manage.py check`: no issues; migrations `0053`–`0057` all `[X]`; Astrakriti plugin registered; `/login/` HTTP `200`; protected companion health `connected`. | PASS |
| Accepted Task unit metadata (read-only) | Read the accepted Task DSM without calculating/saving a measurement: CRS EPSG:32615, horizontal unit `metre`, band units `(None,)`. Runtime unit context reports `m³`, Z unit `metre` with source `assumed from projected CRS; DSM band unit is absent`, vertical datum `unknown`, and the limitation text. Measurement row count remained `0`. No Task, artifact, permission, or measurement data was changed. | PASS |
| Browser presentation of new caveat | Native popup and saved Measurements-list caveat are implemented and included in the deployed bundle; no authenticated browser replay was performed in this continuation. | VERIFICATION GAP |

The historical valid-DSM numeric/control, persistence/restart, permission and
export evidence remains valid and was not repeated. This deployment qualifies
the unit semantics; it does not freshly replay the viewer acceptance flow or
clear the remaining full-goal browser, accessibility, visual and test-suite
verification gaps.

## Task-volume result authorization — 2026-09-19 22:57 Asia/Calcutta

The async volume-result endpoint previously inherited the generic worker view's
`AllowAny` policy and loaded its Task without WebODM's Task visibility check.
It now calls `TaskView.get_and_check_task` before polling or returning output.
Public Tasks retain WebODM's existing public-read behavior; private Tasks
require normal Project access. The numeric output contract and `unit_context`
are preserved.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Focused volume/security regressions | Isolated built-image Django run: `Ran 7 tests in 2.140s — OK`. Includes authorized numeric result plus unit context, denial for another user's private Task, unit conversion/qualification, geographic CRS rejection, and NoData. Test database was destroyed. | PASS |
| Pre-deploy safety check | `queued_or_processing=[]`, `worker_pending=[]`. Accepted Task remained status `40`, non-partial; its Project is private and non-editable publicly; saved measurement rows `0`. | PASS |
| Deployment | Recreated only webapp/worker on image `sha256:11464cdbbb4cab8c531e6826c32770dc35dd15d413935e601abfba446a715285`; database, broker, NodeODM, companion and media volume were untouched. | PASS |
| Post-deploy service health | Django check clean, migrations `0053`–`0057` applied, plugin registered, `/login/` HTTP `200`, companion connected. | PASS |
| Live private-task denial | The accepted Task is itself `public=True` (while its Project remains private), so unauthenticated read follows WebODM's public-Task policy and is not a valid private-denial probe. The isolated private Task regression returned `404` for a foreign user. No private live Task was created for this check. | PASS (fixture); no live private-task probe |
| Accepted data integrity | Read-only query after rollout: Task still status `40`, non-partial, Project `2`, Project sharing flags false, measurement count `0`; queued/processing and worker pending counts `0`. | PASS |

This closes the result-view authorization implementation gap and adds focused
proof. Browser-level display of the unit caveat and the remaining broader
acceptance items are still open; this is not a full-goal completion claim.

## Task-scoped volume progress polling — 2026-09-19 23:05 Asia/Calcutta

Follow-up review found that both measurement clients still polled the generic
`/api/workers/check/<celery-id>` endpoint, which does not know the owning Task.
Added `/api/plugins/measure/task/<task>/volume/check/<celery-id>`; it applies
WebODM's `get_and_check_task` before delegating to the existing worker status
handler. Both Astrakriti's native map workflow and WebODM's Measure popup now
use this Task-scoped route. Other WebODM users of `Workers.waitForCompletion`
retain the original default URL.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Focused volume/security regression set | Isolated current-image Django run: `Ran 9 tests in 3.331s — OK`. Includes both private-Task denial paths (status and result), authorized status/result handling, numeric-output/context contract, units, unsupported CRS, and NoData. Test database destroyed. | PASS |
| Frontend checks | `node --check app/static/app/js/classes/Workers.js`; `node --check coreplugins/astrakriti3d/public/main.js`; `git diff --check` passed. The image build compiled the native Measure popup. | PASS |
| Built/deployed image | Build completed, image `sha256:26c6d6f0e5f6e9ab530322275660d0856bc187877db26cd3ed06049fd4b816fd`; only webapp/worker were recreated. | PASS |
| Safe deployment gate | Immediately before deployment: no queued/processing Tasks and no worker-pending IDs. Accepted Task stayed completed/non-partial, Task-public read enabled as before, Project private/non-editable publicly, measurement count `0`. | PASS |
| Post-deploy behavior/health | `/login/` HTTP `200`; unauthenticated GET of the Task-scoped check route for the accepted Task returned `{"ready":false}` (that Task is already public-read). Django check clean; plugin registered; companion connected. | PASS |
| Data integrity after deployment | Read-only query confirmed accepted Task identity/status/public flag, Project sharing flags, `0` measurements, no queued/processing work, no worker-pending IDs. | PASS |

The private-task authorization assertion is exercised in an isolated test
database; no live private Task was created. The accepted Task's public-read
setting was not changed. This closes the async volume status-polling boundary,
but does not replace the outstanding browser interaction, accessibility,
visual-reference or full-suite acceptance work.

## Task/job binding for volume polling — 2026-09-19 23:16 Asia/Calcutta

Task access alone did not prove that a supplied Celery ID belonged to that
Task. Volume start now returns a short-lived Django-signed binding of the Task
UUID and Celery job ID. Both status and result routes require that binding in
`X-Volume-Job-Token`, verify its signature/age/scope, and recheck WebODM Task
visibility. The token is held only in client memory and is not placed in a URL
or persisted with measurements. Other WebODM `Workers.waitForCompletion`
callers retain the original behavior and URL.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Focused current-source regressions | Isolated built-image Django run: `Ran 11 tests in 3.474s — OK`. Covers token issuance, valid token use for polling/results, mismatched Task/job rejection before Celery access, private-Task denial, separate horizontal/vertical conversion, unknown-unit disclosure, geographic CRS rejection, and NoData. Disposable test DB destroyed. | PASS |
| Client/build checks | Node syntax checks for `Workers.js` and Astrakriti `main.js`; WebODM image build compiled the Measure popup; `git diff --check` passed. | PASS |
| Safe rollout and image | No queued/processing Tasks or worker-pending IDs before rollout. Image `sha256:9dd85bd1589d65b846db8e3bb6fa8945ceb66cc39d7c79deb8504dfae8b0727a`; only webapp and worker recreated. | PASS |
| Post-deploy health | Both services use the new image; Django check clean; migrations `0053`–`0057` applied; plugin registered; companion connected; `/login/` HTTP `200`. | PASS |
| Live missing-token rejection | On the already-public-read accepted Task, GETs to the Task-scoped check and result endpoints without `X-Volume-Job-Token` each returned HTTP `404`. These reads created no worker jobs or measurement rows. | PASS |
| Accepted data and permissions | Task remains status `40`, non-partial, Task `public=True` as before; Project remains `public=False`, `public_edit=False`; measurement count `0`; no queued/processing work or pending worker IDs. No Task, sharing, or measurement data was changed. | PASS |

The accepted Task was not used to create a volume job. Valid signed-token API
behavior and cross-Task mismatch denial are covered by isolated tests; the
live check verifies missing-token denial on a public-read Task. Full browser
measurement replay and the remaining broad accessibility/visual/test gates
remain outstanding.

## Current companion configuration and browser gate — 2026-09-19 23:21 Asia/Calcutta

| Deployed companion configuration | Read-only `manage.py shell` check reported `url_configured=True`, `token_configured=True`; no secret values were printed. `AstrakritiCompanionClient(timeout=3).health_payload()` returned `{'status': 'connected', 'detail': 'Protected Astrakriti preparation service is ready.'}`. The current deployment is therefore configured; earlier time-stamped `NOT_CONFIGURED` observations describe the historical state at those checks and are not current. | PASS |
| Browser workflow access | This historical request reached the sign-in page before the user-authorized sign-in. Subsequent authenticated Docker-origin runs loaded New Reconstruction successfully. | PASS (later authenticated browser evidence supersedes this checkpoint) |
| Video/SRT end-to-end browser workflow | Later authorized disposable browser runs prepared video/SRT, reviewed the 52 candidates across pages, committed a selected set, and created a completed native WebODM Task; see the 2026-09-20 disposable acceptance sections. | PASS |
| Accepted Project 2 / Task integrity | This check made no Task, measurement, permission, or sharing changes. | PASS |

## Login-origin diagnosis — 2026-09-20

| Browser URL and origin | The in-app tab was at `http://127.0.0.1:8000/login/`, origin `http://127.0.0.1:8000`; its form action was `/login/` and its loaded WebODM JavaScript bundle was `main-c9bb443860585622f0d9.js`. | PASS |
| Host-published WebODM instance | Host GET `http://127.0.0.1:8000/login/` returned HTTP `200`, `Server: waitress`, title `Login - WebODM`, and the same `main-c9bb443860585622f0d9.js` bundle. Docker inspection showed host port `8000` published only by Compose service `webapp`, container `87e415448975`, image `sha256:9dd85bd1589d65b846db8e3bb6fa8945ceb66cc39d7c79deb8504dfae8b0727a`. At this point same-bundle evidence was incorrectly treated as proving instance identity; the subsequent route/API comparison below supersedes that inference. | VERIFICATION GAP |
| Direct login on that deployment | A local HTTP session against the running WebODM login endpoint authenticated `astrakriti_acceptance`, received a session cookie, and then loaded `/astrakriti/new-reconstruction/` with HTTP `200`. No password was recorded in this evidence. | PASS |
| Browser stale-page diagnosis | The browser continued displaying the old `Invalid credentials` response on reload, but a fresh GET to `/login/?diag=20260920` showed a clean login form. This alone did not establish which deployment served the browser request; the later authenticated route/API comparison below supersedes the initial stale-page inference. | VERIFICATION GAP |
| Browser cookie management | The supported browser tab exposes only `pageAssets` and `webmcp` capabilities; it provides no cookie/session clear API. No cookies were cleared. The same-origin fresh GET reinitialized only the login page. | PASS (scope limitation recorded) |
| Data safety | No Project, Task, sharing, permission, or measurement data was changed during this diagnosis. No password reset was needed. | PASS |

### Authenticated browser route discrepancy — 2026-09-20

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Browser endpoint behavior | The in-app browser at `http://127.0.0.1:8000` rendered 404 for the plugin route/API and no ASTRAKRITI link. Later listener inspection proved this was the separate Windows-installed WebODM instance; `http://localhost:8000` reaches the Docker deployment. | PASS (origin mismatch diagnosed; wrong-origin 404 is not a Docker product failure) |
| Host-published deployment | `docker compose ps` identifies the sole host-published service on port 8000 as `webapp`; `docker inspect webapp` shows the running WebODM image and only the persistent media volume, with no alternate source bind mount. Webapp startup registers `coreplugins.astrakriti3d.plugin`; database config has `astrakriti3d.enabled=True`. | PASS (local Docker deployment identity) |
| Restart and route table | With zero queued/running Tasks and `worker_pending=[]`, only `webapp` was restarted. After startup settled, an anonymous request directly through its Gunicorn socket to `/astrakriti/overview/` returned the expected login redirect (302), not 404. | PASS (local deployment route registered) |
| Authenticated local HTTP comparison | A short-lived session created with Django's existing acceptance account was sent only to local `127.0.0.1:8000`; the actual HTTP server returned `200` for `/dashboard/`, `/astrakriti/overview/`, `/astrakriti/new-reconstruction/`, and `/api/plugins/astrakriti3d/health/`. Both diagnostic session rows were removed immediately; no password/cookie value was printed. | PASS (local deployment routes and API) |
| Browser instance identity | Listener/process inspection identified `127.0.0.1:8000` as the separate Windows WebODM/Waitress instance, while `localhost:8000` resolves to the Docker Desktop nginx path and registered plugin route. | PASS (origin mismatch identified) |
| Data safety | No Project, Task, sharing, permission, or measurement data was changed. The only restart was the webapp container; database, worker, companion, and media volume were not recreated. | PASS |

Conclusion: the browser and local Docker endpoint do **not** behave as the same
serving deployment. Local `127.0.0.1:8000` resolves to Compose `webapp` and serves
the registered plugin; the in-app browser's `127.0.0.1:8000` endpoint serves a
WebODM page/API surface without those plugin routes. Its actual container or
proxy identity is unavailable through the supported browser diagnostics. Stop
browser acceptance here; do not reset credentials or clear cookies, because
the mismatch is endpoint routing, not demonstrated bad credentials.

### Loopback origin resolution and corrected browser route — 2026-09-20

Read-only listener inspection resolved the serving-process ambiguity above:

| Check | Concrete evidence | Status |
| --- | --- | --- |
| `127.0.0.1:8000` listener | `Get-NetTCPConnection -LocalPort 8000 -State Listen` maps IPv4 `0.0.0.0:8000` to PID `55264`, `python.exe`, executable `C:\WebODM\resources\app\apps\python39\python.exe`. `curl.exe --noproxy "*" http://127.0.0.1:8000/astrakriti/overview/` returned `404`, `Server: waitress`. This is the separate Windows-installed WebODM instance, not the Compose container. | PASS (origin mismatch identified) |
| `localhost:8000` listener/route | `localhost` resolved through the Docker Desktop loopback path (`::1` / `wslrelay.exe`); the same plugin route returned `302`, `Server: nginx/1.30.5`, `Location: /login/?next=/astrakriti/overview/`. The redirect, rather than 404, confirms the plugin route is present behind WebODM authentication. | PASS (correct plugin route identified) |
| Docker deployment identity | `docker inspect webapp` returned container ID `87e41544897597cd3edf7b3e59f9834193c368fffe850af321c552fba16d31b6` and image `sha256:9dd85bd1589d65b846db8e3bb6fa8945ceb66cc39d7c79deb8504dfae8b0727a`. | PASS |
| In-app browser on the corrected origin | At this checkpoint the Docker-origin tab was unauthenticated. A later user-authorized sign-in at `localhost:8000` reached Dashboard and ASTRAKRITI3D pages; disposable acceptance runs then succeeded on that origin. | PASS (later correct-origin authentication supersedes this checkpoint) |
| Acceptance-data integrity | No Project, Task, submission, measurement, permission, sharing, cookie, or credential data was changed. No disposable acceptance data has been created in this continuation. | PASS |

The route discrepancy is resolved: use `http://localhost:8000` for the
Docker-backed ASTRAKRITI3D deployment. At the time of this diagnosis the
correct-origin browser was unauthenticated; the later authenticated browser
check is recorded below.

### Authenticated in-app browser on Docker origin — 2026-09-20

After the user authorized use of their WebODM account for this sign-in, the
supported in-app browser authenticated at the Docker-backed `localhost` origin.
The credential was not written to this log. All checks below were read-only;
Project `2` and accepted Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6` were not
modified.

| Check | Browser action and concrete result | Status |
| --- | --- | --- |
| Correct-origin authentication | Opened `http://localhost:8000/login/`, submitted the user-authorized account in the browser, and observed navigation to `http://localhost:8000/dashboard/` with title `Dashboard - WebODM`. The older `127.0.0.1:8000` tab remained a separate Windows WebODM instance. | PASS |
| Product shell and real records | Opened `/astrakriti/overview/`; title/heading were `OVERVIEW`, ASTRAKRITI3D global navigation was present, companion/WebODM/storage health displayed `CONNECTED`, and six real reconstructions appeared. The accepted Task row linked to the same Task UUID. | PASS (route/data binding; not a full route-matrix rerun) |
| Accepted Run read-only | Opened `/astrakriti/runs/e99b8afd-ab89-4a4b-9d63-2544ca3a18d6/`; it rendered `RUN OVERVIEW`, native state `COMPLETED`, the matching Task UUID, and 7 available outputs. No action was invoked. | PASS |
| Map workspace read-only | Opened the accepted Task `/map/` route. Initial load state cleared after 5 seconds; the viewer exposed Orthophoto, Plant Health, Surface Model, layer/base-map, measure, zoom, and full-screen controls. It reported CRS `WGS 84 / UTM zone 15N`, units `m`, DSM volume `AVAILABLE`, and artifact revision prefix `043f46bc0452`. The measurements section showed no saved rows. This DOM check does not independently prove rendered raster pixels; the prior real-artifact visual acceptance evidence remains the authority for that claim. | PASS (route/control/metadata); rendered pixels rely on prior valid evidence |
| Potree workspace read-only | Opened the accepted Task `/model/` route and waited 5 seconds. Native `potree_render_area`, Point Cloud/Textured Model selectors, Cameras, Appearance, Tools, Clipping, Navigation, Scene, and Filters controls were present; the UI runtime speed updated to `135.7`. Task CRS/revision matched Map. This snapshot does not independently prove visible point-cloud geometry; prior real-scene visual evidence remains the authority for that claim. | PASS (route/native controls); geometry remains backed by prior valid visual evidence |
| Measurements empty state | Opened `/measurements/`; task-scoped workspace showed native Map/3D links and `No saved measurements for this Task.` This is the intentionally cleaned state and was not treated as evidence against the previously validated persistence/export results. | PASS (truthful empty state) |
| Data integrity | No Project, Task, submission, measurement, permission, or sharing operation was performed. No disposable acceptance data was created in this read-only continuation. | PASS |

This resolves the browser-origin/authentication prerequisite and adds fresh
correct-origin route evidence. It does not replace the visual-reference
comparison, full accessibility matrix, full regression, or the explicitly
preserved historical measurement evidence.

### Disposable authenticated browser video/SRT acceptance — 2026-09-20

The user explicitly authorized disposable acceptance Projects, Tasks, uploads,
submissions, and related artifacts, with cleanup after each test. All browser
work used the authenticated Docker-backed `http://localhost:8000` origin. The
accepted Project 2 / Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6` was not used or
modified. The authenticated account's password is deliberately omitted.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Browser video/SRT preparation and Task submission | Uploaded a remuxed 5.005-second, original-resolution clip (5,472×3,078) derived from fixture `fixtures/phase4_dji_0142_0_60/DJI_0142.MP4`, with its matching `DJI_0142.SRT`. The browser preparation review presented five timestamped GPS-matched frames; all five were selected and submitted once. | PASS |
| Real WebODM reconstruction | Disposable Project 22 `Disposable Original Resolution Video Gate 2026-09-20`, Task `bcfd379b-65ef-42d9-a481-4cdbb744237b`, Run `DJI 0142 Five Second Video SRT`. WebODM Task reached `COMPLETED`, progress `1.0`, `images_count=5`, non-partial, no error. Observed progress samples advanced RUNNING `0.153` → `0.3978` → `0.6885` → COMPLETED `1.0`. | PASS |
| Native outputs | Run page listed `cameras.json` (461 B), `georeferenced_model.laz` (751.7 KB), `orthophoto.tif` (30.1 MB), `report.pdf` (3.2 MB), `shots.geojson` (2.2 KB), and `textured_model.glb` (3.1 MB). | PASS |
| Frame review | Five imported source frames were shown at 5,472×3,078 with GPS matches. Quality was truthfully `NOT MEASURED`; R2/coverage advisories and altitude vertical datum were explicitly unavailable/unknown. No quality validation was inferred from successful processing. | PASS (ingestion/review and truthful unavailable states) |
| Telemetry review | Parsed 1,799 records; 0 invalid, 0 ignored; five matched frames and 0 unmatched frames. Reported source range `00:00:00.000`–`00:00:59.989`; frame associations were visible. Altitude vertical datum and camera/gimbal orientation remained explicitly unknown. | PASS |
| Map and 3D render | Disposable Task Map showed actual orthophoto pixels, CRS WGS 84 / UTM zone 37N; DSM/volume was honestly `UNAVAILABLE` because this output set had no DSM. Potree displayed visible point-cloud geometry and native controls. | PASS (orthophoto and point-cloud rendering; DSM absence is a truthful unavailable state) |
| Invalid tiny-input diagnostic | A separate disposable 3-second, 3-frame low-resolution upload successfully exercised browser extraction/GPS review and submission, but WebODM rejected the unsuitable dataset with native `Cannot process dataset`. This is not counted as successful reconstruction evidence or as an implementation defect. | PASS (failure state surfaced; not a successful-run claim) |
| Cleanup and integrity | Deleted only the explicitly disposable Project 22 through WebODM's project API (HTTP 204). Read-only ORM/filesystem checks confirmed Project 22, its Task, Astrakriti submission, and Task media directory were absent. The earlier disposable Project 21 / Task were likewise deleted and verified absent. Temporary remux and temp directories were removed. No measurement rows were created. Project 2 / accepted Task, permissions, measurements, and historical evidence remained untouched. | PASS |

The successful disposable video/SRT browser workflow closes that specific
acceptance gate. It does not freshly replay the historical measurement,
persistence/reload/restart, permission, or export evidence; those previously
validated results remain the evidence for those behaviors. Full visual-reference
comparison, accessibility, and broad regression gates remain separate work.

### New Reconstruction accessibility sample — 2026-09-20

Using the authenticated browser session on `http://localhost:8000` (the
Docker-backed instance), opened `/astrakriti/new-reconstruction/` without a
login redirect. This was a read-only keyboard/semantics check: no file chooser,
validation submission, preparation, Project creation, or Task submission was
triggered.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Page semantics | Browser DOM exposed one `main`, two `nav` landmarks, one H1 (`NEW RECONSTRUCTION`), and one H2 (`Native WebODM reconstruction intake`). Every form control had an associated HTML label; the two mission/run text inputs were marked required. No image was missing an `alt` attribute. | PASS (this page/sample only) |
| Visible control names | The New Reconstruction form controls and actions had names; a visibility-filtered DOM scan found no unnamed visible links. (An earlier raw scan included two non-visible native header anchors; they are not counted as visible control failures.) | PASS (visible-control sample only) |
| Keyboard-only focus | Starting from page load, Tab traversed shell navigation, the New Reconstruction links, project/input selectors, required name fields, all three file inputs, preparation mode, `Validate and prepare inputs`, and `Use a new submission identity` without activating them. Focus styling was observed on the active navigation item, form controls, and buttons. | PASS (focus order/reachability on this page) |
| Responsive overflow sample | At the browser's actual `1280×720` viewport, `window.innerWidth=1280`, `documentElement.clientWidth=1265`, `documentElement.scrollWidth=1265`, and body width/client width were both `1265`; no horizontal overflow. This is not the specified `1280×800` screenshot viewport and does not replace the prior exact viewport matrix. | PASS (current-view overflow only) |
| Console errors | `astraTab.dev.logs({levels:["error"], limit:20})` returned no entries while on this healthy form route. | PASS (captured browser-console errors for this visit) |
| Overall accessibility compliance | Contrast, 200% zoom, status announcements, dialog handling, reduced motion across pages, native Map/Potree keyboard/touch operation, and the full page-by-page accessibility matrix were not established by this sample. | VERIFICATION GAP |

This closes only the bounded New Reconstruction keyboard/semantics sample. It
does not change the release gate for full accessibility verification.

### Overview visual sample — 2026-09-20

Captured and inspected the current authenticated Docker-backed Overview in the
in-app browser at its actual `1280×720` viewport. DOM title was
`OVERVIEW - WebODM`; the route rendered the connected system strip, Overview
identity, honest no-active-reconstruction state, New Reconstruction action,
and a ruled Recent Reconstructions table with real WebODM statuses and IDs.
The screenshot visibly follows the written `design.md` foundation in its warm
neutral canvas, narrow navigation rail, thin utility line/rules, graphite
primary action, subdued active navigation, and open list/table treatment. The
current idle state has no fabricated active Run or progress. No obvious crop
or horizontal page overflow was visible at this viewport.

| Check | Evidence limit | Status |
| --- | --- | --- |
| Written-system visual sample | One live Overview screenshot at 1280×720 was visually inspected inline against the written `design.md` traits; this is not the specified 1280×800 or 1440×900 comparison and does not cover every page/state. | PASS (bounded visual traits only) |
| Approved reference inventory | The later complete inventory parsed all 13 approved PNG paths from `AI-HARNESS-GOAL.md` and confirmed every path and `design.md` exists. This supersedes the earlier incomplete search recorded here. | PASS (inventory only) |
| Approved-image comparison | Only a bounded Overview sample was compared visually against the written system. Same-state page-by-page comparisons across all 13 references and four required viewports remain undone. | VERIFICATION GAP |
| Screenshot archive | The in-app browser returns transient screenshot data but exposes no supported workspace-save operation; no archive was produced. | UNSUPPORTED (archive mechanism only) |

Do not treat the visual sample as completion of the goal's full visual QA.
Same-state comparison against the approved reference images at required
viewports, and final screenshot archiving, remain open.

### Account identity and Potree keyboard accessibility — 2026-09-20

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Requested account on Docker origin | In the in-app browser, `http://localhost:8000/astrakriti/overview/` loaded without redirect and the WebODM account menu displayed `Hello, phase1admin!`. Browser inventory showed this authenticated tab on `localhost:8000`; the separate user tab on `127.0.0.1:8000` remained the Windows WebODM instance. No credential was re-entered, reset, or logged. | PASS |
| Accepted Task boundary | Opened only the accepted Task's read-only `/model/` route, UUID `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6`. The check used DOM/accessibility inspection and Tab only; no mouse activation, viewer manipulation, measurement, export, save, or Task/permission mutation occurred. | PASS |
| Potree measurement/clipping keyboard access | The original snapshot found native controls unreachable; the later remediation converted tool icons to named buttons. A subsequent bounded live traversal reached Distance, Area, Volume, Orbit, clipping, and view controls by keyboard. | PASS (targeted remediation; full accessibility remains open) |
| Potree scene alternative | The original canvas lacked a name/description; later browser inspection exposed a focusable named scene with linked task-specific description. | PASS (targeted remediation) |
| Potree icon-only controls and sliders | The later deployment exposed a named download button and focusable slider handles with slider roles, labels, current values, and bounds. | PASS (targeted remediation) |

These findings prevent full accessibility sign-off under the goal's explicit
native-viewer keyboard/accessibility criteria at the time of this observation.
The subsequent scoped remediation and live results are recorded in the
"Map/Potree accessibility remediation" section below. Full application-wide
accessibility sign-off remains separate.

### Map keyboard/accessibility sample — 2026-09-20

On the same accepted Task Map route, waited for the viewer to settle (the
initial `Loading...` state cleared after five seconds), then inspected controls
and used Tab only. Console error capture returned no entries. No tool was
activated and no measurement was drawn or saved.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Keyboard-reachable Map controls | Tab reached named Orthophoto, Plant Health, Surface Model, Layers, Base Maps, Crop, Object Detection, Contours, Measure volume/area/length, View Fullscreen, Zoom in/out, unit selector, snapshot, Share, and 3D controls. | PASS (focus reachability only; no operation was invoked) |
| Opacity control label | This original observation found no programmatic label; later correction associated the range with `Map layer opacity` and wrapped the generated imagery-popup slider in a label. | PASS (targeted remediation) |
| Map text alternative | The original map region lacked a name/description; later browser inspection exposed a named region with linked keyboard instructions and task/layer context. | PASS (targeted remediation) |
| Accepted Task data | Map panel still reported `No saved measurements for this Task.`; only route navigation and Tab focus were used. | PASS (read-only boundary) |

These Map findings were present at the time of this observation; see the later
"Map/Potree accessibility remediation" section for the deployed correction and
live verification. Full accessibility compliance remains unverified and cannot
be signed off.

### Current deployment and migration snapshot — 2026-09-20 12:33 Asia/Calcutta

Read-only live checks (`docker compose ps`, `showmigrations app`, and
`manage.py check`) reported all six Compose services Up (`webapp`, `worker`,
`db`, `broker`, `node-odx-1`, and `astrakriti-companion`), the
`coreplugins.astrakriti3d.plugin` registered, migrations 0053–0057 applied,
and `System check identified no issues (0 silenced)`. Compose emitted only the
existing obsolete `version`-attribute warning. This is live service/schema
health evidence, not a clean rebuild, full-suite test, or release sign-off.

### Authenticated route and empty-state sample — 2026-09-20 12:42 Asia/Calcutta

Using the already-authenticated `phase1admin` session at the Docker-backed
`http://localhost:8000` origin, opened the global routes Overview, Missions,
Reconstructions, Artifacts, Reports/Exports, Processing/Recovery, System,
Settings, and New Reconstruction. Each returned its expected ASTRAKRITI3D
page heading and global navigation without an authentication redirect. The
System/Settings view reported WebODM session, processing node, storage, and
companion connected; global worker health was explicitly `unknown` because
this WebODM revision has no supported global worker-health endpoint. No
Project, Task, input, permission, sharing, or measurement operation was
performed.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Mission search and sort | On `/astrakriti/missions/`, typing `Phase 1 Untouched Fixture` reduced the table to that one matching row; keyboard-clearing restored all four rows. Selecting `Name A–Z` produced `First Project`, `First Project`, `Phase 1 Untouched Fixture`, `Test` order. | PASS (bounded list controls) |
| Mission contextual routes | Mission 20 detail loaded `MISSION OVERVIEW`; its observed Overview/Runs/Artifacts/Reports/Files links each opened the corresponding page heading. Mission 20 showed one linked Run, `457655b0-91d8-4f14-a804-fd87e3587f5c`. The Project description and unrecorded context/provenance were distinguished; no context-save action was invoked. | PASS (route/navigation and truthful context state) |
| Run contextual routes | Run `457655b0-91d8-4f14-a804-fd87e3587f5c` displayed Overview/Frames/Telemetry/Map/3D Model/Measurements/Validation/Reports/Files links with matching destinations. Corresponding views loaded. | PASS (route/navigation) |
| Empty/unavailable run state | This existing Run reports lifecycle `UNKNOWN`, no available artifacts, no saved measurements, `DSM volume: UNAVAILABLE`, and Validation accuracy/scale `NOT VERIFIED`; no result was inferred from the viewer shell. The Data/Review pages rendered their route headings. | PASS (honest state display only; not a positive artifact-render claim) |
| Console errors | Captured browser console error entries after the route sweep: none. This does not cover all routes, actions, or failure paths. | PASS (bounded sample) |
| Browser access identity | The user-provided localhost browser session remained authenticated without credential entry; the separate user tab at `127.0.0.1:8000` was not used. | PASS |

This is a route, list-control, and empty-state sample—not the full E2E matrix,
visual viewport matrix, or screen-reader/accessibility sign-off. It creates no
new acceptance data and does not change the previously recorded real-task
measurement evidence or the accepted Task.

### Map/Potree accessibility remediation — 2026-09-20

This is a scoped correction to the concrete native-viewer defects recorded
above, not a full accessibility sign-off. All checks used the Docker deployment
on `http://localhost:8000`. The accepted Task was accessed through its existing
read-only public Map/3D routes; no control was activated, and no Project, Task,
permission, sharing, or measurement data was changed.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Map accessible name and description | Public Task Map route exposed a named region, `Map showing Orthophoto for Morris Thomas Road - 01/08/2016`, with a linked keyboard instruction description. | PASS |
| Map opacity | The range control is announced as `Map layer opacity`; its label is programmatically associated. The generated imagery-popup opacity control is also wrapped in a label. | PASS |
| Potree controls | Measurement, clipping, and navigation icons are native buttons with localized hidden text names. The viewer canvas is a focusable named image with a Task-title description; the download dropdown has the name `Download available assets`. | PASS |
| Potree sliders | Appearance and navigation sliders are exposed with slider roles, names, current values, bounds, and keyboard focus. The sampled names included Point budget, Field of view, Radius, Strength, Opacity, Min node size, and Speed. | PASS |
| Keyboard reachability | Sixty-three Tab presses over two traversals, with no activation, included the canvas itself and traversed the observed Appearance controls plus measurement, clipping, and navigation groups. Distance, Area, Volume, Orbit, clipping, and view controls appeared as focusable named buttons. | PASS (bounded native 3D route) |
| Focus styling | The 3D canvas and Potree tool buttons have visible mineral-blue keyboard focus outlines in the rebuilt ModelView/Potree CSS. | PASS (source/build; broad visual QA remains open) |
| Focused frontend regressions | In network-isolated image `webodm/webodm_webapp:astrakriti-a11y-title`, Jest ran `Map.test.jsx` and `AssetDownloadButtons.test.jsx`: 2 suites, 4 tests passed. Existing warnings were emitted by Standby's legacy lifecycle and a LayersControlButton `javascript:` URL. | PASS |
| Production build | Webpack 5.89 compiled the final MapView/ModelView bundles and `collectstatic` completed. Existing bundle-size, deprecation, and static-path collision warnings remain. | PASS (build) |
| Deployment and integrity | Only `webapp` was recreated, now image `sha256:6743daa6a30204f484e15de7ad8a65ea2f07a5c6a14d054cb9d8fd88d3d70abe`; worker, database, broker, companion, NodeODM, and media volume were not recreated. Django check was clean; migrations 0053–0057 remain applied. Read-only query confirmed accepted Task status 40, non-partial, zero measurement rows, and Project 2 `public=False`, `public_edit=False`. | PASS |
| Map output pixels / measurement replay | This accessibility replay did not wait for the Map's initial Loading state to clear or draw measurements. Prior valid real-artifact and measurement/persistence/export evidence remains authoritative; no acceptance replay was repeated. | Not retested here (prior evidence retained) |
| Full accessibility and visual gates | Other pages, all viewport sizes, screen-reader output, contrast/zoom, dialog handling, reduced motion, and the full design-reference comparison were not covered by this correction. | VERIFICATION GAP |

The browser tab was unauthenticated after the Docker Desktop restart, so the
native public Task routes were used for read-only Map/Potree verification. The
correct-origin `phase1admin` account verification is recorded earlier in this
log; this section does not claim a fresh authenticated-shell route sweep.

### Correct-origin sign-in resumed — 2026-09-20 14:43 Asia/Calcutta

The in-app browser was signed in at the Docker-backed `http://localhost:8000`
using the user-authorized `phase1admin` account. The login form navigated to
`/dashboard/`; opening `/astrakriti/overview/` on that same origin loaded the
ASTRAKRITI3D Overview without redirecting back to login. The live Overview
showed WebODM, processing, and storage as `CONNECTED`, six visible Task rows,
and the accepted Task ID `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6`. This confirms
the browser session is authenticated against the intended Docker deployment.
On the same authenticated session, the WebODM account menu explicitly showed
`Hello, phase1admin!`. The credential is not recorded here. No Project, Task,
permission, sharing, submission, or measurement operation was performed in
this sign-in check.

### Approved reference availability and live Overview sample — 2026-09-20 14:47

Rechecked the exact 13 approved PNG paths listed in
`C:\Users\Yashwanth\ai mentor\AI-HARNESS-GOAL.md`: every path exists. The
referenced `design.md` also exists. This supersedes earlier entries that said
the approved files could not be found; those entries reflected an incomplete
inventory, not missing user assets.

Captured and inspected the live Docker Overview in the in-app browser at its
current 1265×720 content viewport. It showed the real idle state, six current
Task rows, and native data rather than screenshot-derived sample values. The
approved Overview image depicts a different state (one active reconstruction),
so its progress values and active-work layout are not valid targets for this
idle live state. The shared-shell comparison is only a bounded visual sample,
not a same-state or same-viewport match. The in-app browser screenshot API
returns transient screenshot bytes but exposes no supported operation to save
those bytes into the workspace; no screenshot archive was produced.

| Check | Evidence and limit | Status |
| --- | --- | --- |
| Approved source inventory | Parsed all 13 PNG paths from the goal and checked each with `Test-Path`; all returned `True`. The prescribed `design.md` path also returned `True`. | PASS (sources available) |
| Current Overview screenshot | Browser screenshot from `http://localhost:8000/astrakriti/overview/`, captured and visually inspected at the in-app browser's current 1265×720 content viewport. | PASS (bounded capture only) |
| ASTRAKRITI brand mark | At this 14:47 observation the live screenshot showed the boxed `A3` placeholder. The source was subsequently replaced with the approved-reference geometric terrain mark and deployed; see “Approved geometric brand mark implementation and deployment” below. The current live visual comparison remains a verification gap because the Docker-origin browser tab redirects to login. | VERIFICATION GAP (visual confirmation only; source gap resolved) |
| Full visual-reference gate | No local screenshot archive or exact viewport override is exposed by the supported in-app browser controls. Only one live page/state was captured; required same-state comparisons across 13 pages and 4 viewports remain undone. Historical `UNSUPPORTED` claims based on missing image files are withdrawn; the accurate status is VERIFICATION GAP. | VERIFICATION GAP |
| Data boundary | The live Overview was read-only; no Project, Task, permission, sharing, or measurement data was changed. | PASS |

### Disposable cross-page frame selection — 2026-09-20

Ran a bounded browser acceptance check on the authenticated Docker WebODM
origin `http://localhost:8000`. This used only disposable intake data and did
not touch Project 2 or the accepted Task
`e99b8afd-ab89-4a4b-9d63-2544ca3a18d6`.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Video/SRT preparation and candidate listing | Created temporary Project 23 (`Disposable Frame Review 20260920`) and Task `00dc310b-fb93-4ad9-8f7d-6372b3120531` (`Cross-page Selection Test`). The browser prepared a 52-second 640×360 video with the existing DJI SRT and displayed 52 candidate frames, 48 on page 1 and 4 on page 2. | PASS (bounded flow) |
| Cross-page in-memory selection state | Started with 52 selected. Unchecked frame 1 on page 1 (51 selected), navigated to page 2, unchecked frame 50 (50 selected), paged back and forward, and observed both checkboxes still unchecked and aggregate selection still 50. Other page-2 frames remained checked. | PASS |
| Recommendation-dependent choices | R2 and coverage choices were disabled because this short disposable input had no recommendations. This is an unavailable-data state, not evidence those recommendations were selected or processed. | UNSUPPORTED for this input |
| Reload/server persistence of candidate selection | This first Project 23 test intentionally did not commit. The Project 24 follow-up later committed the exclusions, read back 50 selected frames from submission metadata, and verified Frames=50 after Run-page reload. | PASS (later disposable browser verification) |
| Disposable-data cleanup | Project.delete marked the exact Project 23 for cleanup; Task.delete removed the exact partial Task and its media; the now-empty Project was deleted. The exact reserved submission row (`5eec476a-8c17-423c-a68a-a207e09e3b2a`) was removed after its Task and Project references were null. Follow-up queries returned Project 23 absent, Task UUID absent, submission absent, and `/webodm/app/media/project/23` absent. The sole generated derivative `frame-review-52s.mp4` was removed from its exact temporary directory; source video/SRT fixtures were not changed. | PASS |

No new WebODM reconstruction was queued by this check. It establishes the
picker's cross-page client-side selection behavior only; it does not replace
the separately recorded real-artifact, measurement, persistence, reload,
restart, permissions, or export evidence, nor does it close their remaining
verification gaps.

### Disposable saved-selection reconstruction and native viewer replay — 2026-09-20

Follow-up to the client-only picker check above. This run deliberately used a
second private disposable Project/Task on the authenticated Docker origin; it
did not access or modify Project 2 or the accepted Task
`e99b8afd-ab89-4a4b-9d63-2544ca3a18d6`.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Browser preparation and saved frame selection | Project 24 `Disposable Frame Persist 20260920`, Task `6a01f36e-6ca1-4420-95e3-8b38ac824168`, submission `b1d423a3-2ed6-43b3-b0f8-2ca55cc83abf`. The UI prepared 52 candidate frames. Frame 1 and frame 50 were unchecked on separate pages; navigating back and forward retained both exclusions and showed 50 selected. | PASS |
| Selection persistence and application | The UI's single `Save selection and start reconstruction` action committed the Task. The stored submission metadata read back as `strategy=manual`, 52 candidate hashes, 50 selected filenames, `applied=true`, with frames 1 and 50 absent. The native Task had `partial=false`, `images_count=50`, and WebODM status `COMPLETED` (40). | PASS |
| Reload and native lifecycle | Before and after reloading `/astrakriti/runs/6a01f36e-6ca1-4420-95e3-8b38ac824168/`, Run overview showed 50 frames. The live UI transitioned from `RUNNING` / native `processing` to `COMPLETED` / native `completed`; WebODM assigned it to `node-odx-1`. Worker logs identified the exact Task; the completed Run listed six available output files. | PASS (disposable lifecycle/reload) |
| MapView | Direct route `/astrakriti/runs/6a01f36e-6ca1-4420-95e3-8b38ac824168/map/` loaded the real Task orthophoto with visible reconstruction pixels. The measurement sidebar showed CRS `WGS 84 / UTM zone 37N`, units `m`, artifact revision `32bfabc11f66`; browser console error list was empty. This Task's Map reported DSM volume `UNAVAILABLE` and showed no DSM layer. | PASS for orthophoto rendering; UNSUPPORTED for DSM volume on this artifact set |
| Native Potree | Direct route `/astrakriti/runs/6a01f36e-6ca1-4420-95e3-8b38ac824168/model/` rendered the real Task's point cloud visibly on the 396×486 accessible Potree canvas. The run also listed `georeferenced_model.laz` and `textured_model.glb`; browser console error list was empty. | PASS (bounded real-scene render) |
| Native 3D distance and scene persistence | Drew a Potree distance over the visible point cloud; UI label showed `190.07 m`. The WebODM Task's `potree_scene` stored one `Distance` with UTM points `[262884.08599853516, 40150.462005615234, 18.925994873046875]` and `[263023.922000885, 40276.92900085449, -5.163002014160156]`. Independent Euclidean calculation returned `190.0744280777 m` (absolute delta `0.0044281 m`, consistent with 2-decimal display rounding). Reloading the native viewer restored the red segment and `190.07 m` label. This is native Potree scene persistence, separate from the ASTRAKRITI task-measurement sidecar, which correctly remained empty in this run. | PASS (bounded 3D distance/reload) |
| Valid DSM volume | No DSM artifact was among this Task's available outputs; the Map explicitly reported volume unavailable. No volume value was fabricated or measured. Prior valid-DSM measurement evidence elsewhere in this log remains authoritative and was not repeated. | UNSUPPORTED for this Task |
| Test cleanup and data boundary | Project 24 was private (`public=False`, `public_edit=False`). Removed the exact completed WebODM Task through `Task.delete()`, the now-empty exact Project through `Project.delete()`, and its exact submission row. Its NodeODM UUID `744009c1-481a-46d1-a246-09c7dbf5d62e` was confirmed on node `node-odx-1` as `COMPLETED`, then removed through `ProcessingNode.remove_task()`; its `/var/www/data/<NodeODM UUID>` directory is absent. Verified Project 24, WebODM Task UUID, submission UUID, and `/webodm/app/media/project/24` absent. Removed the sole generated derivative from its exact temp directory; original video and SRT fixtures were unchanged. Read-only final query confirmed accepted Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6` still status 40. | PASS |

This closes the earlier candidate-selection reload/server-persistence gap for
the tested intake path and proves a real disposable WebODM Task can reach
completion with the selected 50 frames, survive reload, and render its actual
orthophoto and point cloud. It does not establish application restart
persistence, the full Map/3D layer and interaction matrix, valid-DSM volume on
this dataset, permission isolation across multiple users, or the full visual,
responsive, security, and browser E2E gates; use the separately recorded
evidence and remaining statuses above for those requirements.

### Standard full-image reproducibility recheck — 2026-09-20 15:31–15:35 Asia/Calcutta

Re-ran the standard build once after the earlier pinned FFmpeg transfer
interruption. This was a build/check only: the new image was not deployed, and
the already-running application services were not restarted.

| Check | Command or concrete result | Status |
| --- | --- | --- |
| Standard full WebODM image build | `docker compose -f docker-compose.yml -f docker-compose.build.yml build webapp` exited `0`. The pinned FFmpeg 7.0.2 archive downloaded, passed ZIP validation, and was copied into the image. Final image manifest/image ID: `sha256:de81b875db44879af0509ee61a8c868ff45c5900d60a24088989c8c7e0d59200`. | PASS |
| FFmpeg in built image | `docker run --rm --entrypoint ffmpeg webodm/webodm_webapp:latest -version` reported `ffmpeg version 7.0.2-static`. | PASS |
| Django system check on built image | Disposable Compose run of `python manage.py check` reported `System check identified no issues (0 silenced)` and registered `coreplugins.astrakriti3d.plugin`. | PASS |
| Migration state in current database | Disposable Compose run of `python manage.py showmigrations app` returned `[X]` for `0053_astrakriti_measurement`, `0054_astrakriti_submission`, `0055_astrakriti_preparation`, `0056_astrakriti_legacy_link`, and `0057_astrakriti_mission_metadata`. | PASS |
| Model/migration consistency | Disposable Compose run of `python manage.py makemigrations --check --dry-run` returned `No changes detected`. | PASS |
| Deployment boundary | `docker inspect webapp` still reported running image `sha256:6743daa6a30204f484e15de7ad8a65ea2f07a5c6a14d054cb9d8fd88d3d70abe`, distinct from the new local build. Compose still showed all six services running; no service was recreated. Disposable `webodm-webapp-run-*` containers were removed by `--rm`. | PASS (no deploy/restart) |
| Accepted data integrity | Read-only post-check: Project 2 remained `public=False`, `public_edit=False`; accepted Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6` remained status `40`, non-partial; measurement row count remained zero. No Project/Task/permission/measurement data was written. | PASS |

Webpack performance/deprecation warnings and Compose warnings (obsolete
`version`, volume bind option, and listed orphan services) were non-fatal and
were not altered. The successful build supersedes the older interrupted
transfer as the current source-build result. Because this image was not
deployed, this row is not evidence of a live-service restart using that exact
new image; the currently running `6743daa6…` image has its own successful
deployment, migration, and browser evidence above.

### Approved geometric brand mark implementation and deployment — 2026-09-20 16:01–16:06 Asia/Calcutta

Replaced the shell's boxed `A3` placeholder with a small inline SVG terrain
triangulation derived from the approved Dashboard reference. Retained the
existing ASTRAKRITI3D wordmark, ink color, and shell navigation; used the
approved active mineral color for the symbol. This is a direct match to the
user-provided reference, not a new visual direction.

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Source implementation | `coreplugins/astrakriti3d/templates/app.html` now contains a decorative inline geometric SVG with `aria-hidden=true`; `.astrakriti-brand` in `coreplugins/astrakriti3d/public/astrakriti.css` stacks the symbol above the existing typographic wordmark. | PASS (implemented) |
| Standard image build | `docker compose -f docker-compose.yml -f docker-compose.build.yml build webapp` exited `0`; image manifest `sha256:b1b4e7fdc87044e938a99faa5bc6231f3f32feddf8b5ebc36f10924d8a2a183f`. The output image contains the updated template. | PASS |
| Focused frontend regressions | In the built image, Jest ran `Map.test.jsx` and `AssetDownloadButtons.test.jsx`: 2 suites and 4 tests passed. Existing React lifecycle and `javascript:` URL warnings remain. | PASS |
| Controlled deployment | Recreated only `webapp` and `worker`; both now run image `sha256:b1b4e7fdc87044e938a99faa5bc6231f3f32feddf8b5ebc36f10924d8a2a183f`. Persistent DB/media, broker, companion, and NodeODM were not recreated. | PASS |
| Post-deploy application check | `docker exec webapp python manage.py check` reported no issues and registered the ASTRAKRITI plugin; `showmigrations app` showed 0053–0057 applied. | PASS |
| Deployment preflight/data boundary | Immediately before rollout, Task queries returned 0 queued, 0 processing; worker pending set was empty. Accepted Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6` remained status 40/non-partial; Project 2 remained private and not publicly editable. No Task, Project, permission, sharing, or measurement operation was performed. | PASS |
| Live visual verification | The original open dashboard tab is `http://127.0.0.1:8000/dashboard/`; the Docker deployment is `http://localhost:8000`. A fresh read-only visit to the Docker Task Map redirected to `http://localhost:8000/login/?next=...`, confirming that the 127.0.0.1 session cookie does not authenticate the localhost origin. No login credentials were entered. Consequently the newly deployed brand mark has not yet been visually inspected in the authenticated product shell. | VERIFICATION GAP (origin/session mismatch) |
| Tooling note | Host-side Jest was absent; the attempted `npx jest` resolution to a different version was stopped. The focused tests were then run from the built image without adding dependencies. A standalone `docker run` Django check could not resolve Compose hostname `db`; the post-deploy `docker exec` check above passed in the live Compose network. | PASS (limitation isolated) |
| Follow-up image export attempt | A second build after simplifying the SVG completed Webpack and FFmpeg, exported manifest `sha256:a72c1118888ef70157a1abc7cc4aafc14a20e9ec07e4d6c27786cc953e541dc2`, then failed Docker's final layer unpack with `archive/tar: invalid tar header`. It was not deployed. A source-identical cached rebuild below recovered a valid image tag. | PASS (transient failure superseded by successful rebuild) |
| Source-identical cached rebuild | After restoring the exact deployed source, `docker compose -f docker-compose.yml -f docker-compose.build.yml build webapp` completed with all layers cached, exit 0, manifest `sha256:5d862b6089dbc51000fb7b8e66e8c083326962a45c2e27f465ce72361dc75b4e`. `ffmpeg -version` in the image reports `7.0.2-static`. Image template and CSS SHA-256 values exactly match both the workspace and running `webapp` container. `webapp` and `worker` were not recreated; their earlier live health/check evidence remains current. | PASS (reproducible build/tag restored) |

The source-level A3-mark implementation gap is addressed; exact live visual
matching remains unverified until the browser is signed into the Docker origin.
The pre-existing `127.0.0.1` dashboard tab was not navigated or modified.

### Companion selector deployment and browser-origin diagnosis — 2026-09-20 16:26–16:30 Asia/Calcutta

| Check | Concrete evidence | Status |
| --- | --- | --- |
| Stale companion source | Before deployment, the live companion's `/opt/astrakriti/astrakriti3d/project.py` hash differed from the current source (`bbb250fa…` vs `3db9ac46…`). | PASS (discrepancy confirmed) |
| Focused selector/preparation tests | `python -m pytest tests/test_project_modes.py tests/test_preparation_worker.py -q`: `11 passed`. | PASS |
| Companion rollout | `docker compose -f docker-compose.yml -f docker-compose.astrakriti.yml up -d --build astrakriti-companion` succeeded. New image manifest: `sha256:21d0e26f5a12e8d7c259964e3afd07253ac0f58495cdc60004c401272ab08176`. No WebODM `webapp`, `worker`, Project, Task, permission, measurement, or historical record was changed by this rollout. | PASS |
| Runtime source and persistent queue | The running `project.py` SHA-256 is `3db9ac46205e7febefa2bebc741ce8b0313a9b576f16a299eb6467a7a50d6b2a`, identical to source. Companion `/health` returned HTTP 200 `ready` using its configured service token. Named volume remained `webodm_astrakriti_companion_data`; all four existing preparation jobs remained `completed`. | PASS |
| Deployed selector diagnostic smoke test | In an isolated temp-volume directory, generated a synthetic 4-second video and called the running companion image's `prepare_project` directly in local mode. It produced 4 candidate frames, 4 diagnostic rows (`status=available`, `policy=advisory_only_all_source_frames_retained`, `recommended_count=4`), and retained all 4 frame files. The exact temp directory was removed and its absence verified; no persistent queue record or WebODM Task was created. This is a smoke test, not a recommendation-quality or UI test. | PASS (runtime diagnostic plumbing) |
| WebODM-to-companion integration | `docker exec webapp python manage.py shell -c "from coreplugins.astrakriti3d.companion import AstrakritiCompanionClient; print(AstrakritiCompanionClient(timeout=5).health_payload())"` returned `{'status': 'connected', 'detail': 'Protected Astrakriti preparation service is ready.'}`. This supersedes the earlier `NOT_CONFIGURED` health observation from before the companion environment was active. | PASS |
| Companion runtime hardening | `docker inspect` reported `ReadonlyRootfs=true`, `CapDrop=[ALL]`, `no-new-privileges:true`, and `5001/tcp` with no host binding. The companion requires bearer authorization for `/health`; unauthenticated access returned HTTP 401 in the preceding runtime check. | PASS (deployment configuration and auth gate) |
| Secret exposure spot-check | The configured companion bearer token was checked in-memory, without printing it: none of 290 WebODM frontend source/template/static `.js`, `.jsx`, `.mjs`, `.css`, or `.html` files matched it; 143 lines of recent WebODM/companion container logs contained zero matches. This is a targeted token-leak scan, not a complete security audit. | PASS (bounded scan) |
| Browser URL to deployment mapping | `docker port webapp` reports `0.0.0.0:8000 -> 8000/tcp`. Unauthenticated GETs to `/login/` at both `http://localhost:8000` and `http://127.0.0.1:8000` each returned the same `Login - WebODM` page and `/login/` form action. Both origins therefore address the same currently published Docker webapp in this environment. | PASS (same deployment) |
| Browser session mismatch | Initial browser state showed the `127.0.0.1` tab on `/dashboard/` and the `localhost` tab on `/login/?next=/astrakriti/overview/`. Opening a fresh ASTRAKRITI3D route in a new `127.0.0.1` tab redirected to `/login/?next=/astrakriti/overview/` too, so the old dashboard tab was stale and no active session was established. Browser-origin cookies are host-scoped, but both hosts currently reach the same Docker deployment. The browser automation did not enter credentials or modify either cookie jar; the signed-in account identity was not independently read. | VERIFICATION GAP (browser session) |
| Protected accepted data integrity | Read-only Django ORM query after the companion smoke test: Project 2 remained private with `public_edit=False`; accepted Task `e99b8afd-ab89-4a4b-9d63-2544ca3a18d6` remained status `40`, non-partial, with `0` ASTRAKRITI measurements. Companion queue remained four `completed` records, and no `selector-audit-*` temp directory remained. | PASS |

No browser-driven acceptance flow was replayed in this check; previously recorded
real measurement/persistence/export evidence remains valid, while any requested
fresh replay remains a verification gap.

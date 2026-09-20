# Astrakriti3D + WebODM Implementation Phases

This document preserves the original phased plan, written when WebODM lived
in a sibling checkout. The customized source now ships under `WebODM/` in this
repository; see `INTEGRATION_BOUNDARY.md` for the current layout.

This plan converts the WebODM fork strategy into incremental, verifiable
development phases. The existing Astrakriti3D project remains protected until
the replacement workflow has passed verification.

Implementation note: the production boundary now lives in the maintained
WebODM checkout's `coreplugins/astrakriti3d` plugin. The new
`astrakriti3d.companion_api` is preparation-only (video/SRT/telemetry) and
does not own WebODM Projects, Tasks, authentication, or reconstruction
lifecycle. The live completed-Task/viewer gate is still pending; this document
must not be read as evidence that the live milestones have passed.

The current additive reconciliation path is the WebODM
`astrakriti_reconcile` management command and `AstrakritiLegacyLink` model.
It preserves legacy Mission/Run/Job identities and source payloads, applies
only explicit or exact native identity matches, and records unresolved or
conflicting links for human reconciliation.

## Phase 0 — Baseline and protection

### Objective

Record the current state and protect the working Astrakriti3D pipeline.

### Work

- Confirm the Astrakriti3D branch and clean working tree.
- Run and record the existing Python test suite.
- Record Python, FFmpeg, Docker, NodeODM, and WebODM versions.
- Preserve existing evidence, runs, reports, and configuration.
- Record the dashboard and CLI entry points.

### Exit gate

The existing test suite passes and the baseline is documented before integration.

## Phase 1 — Untouched WebODM runtime

### Objective

Prove that official WebODM works independently before customization.

### Work

- Clone WebODM beside Astrakriti3D.
- Create branch `codex/astrakriti3d-webodm`.
- Record the upstream commit.
- Start the WebODM and processing-node services.
- Verify login, project creation, task processing, map, 3D viewer,
  measurements, and downloads.

### Exit gate

An unmodified WebODM task completes successfully with a small fixture.

## Phase 2 — Integration shell and adapter

### Objective

Create a stable boundary between Astrakriti3D and WebODM.

### Work

- Keep WebODM source and Astrakriti3D source separate.
- Use `integrations.WebODMAdapter` for all WebODM operations.
- Add configuration for application name, theme, URLs, and upstream location.
- Add WebODM and processing-node health checks.
- Document upstream license and attribution requirements.

### Exit gate

Astrakriti3D can perform project creation, task submission, status lookup,
cancellation, asset retrieval, and health checks through the adapter only.

## Phase 3 — Product data model and lifecycle

### Objective

Represent Astrakriti3D product state independently from WebODM internals.

### Work

Implement persistent records for:

- Mission
- Run
- Artifact
- Evidence

Implement the Run state machine:

```text
CREATED → PREFLIGHT → PREPARING → READY → SUBMITTED → PROCESSING → COMPLETED
```

Also support failure, cancellation, partial, and recovery states. Persist
transitions and make retries idempotent.

### Exit gate

A Run can be created, transitioned, recovered after restart, and linked to a
WebODM task without duplicate submissions.

## Phase 4 — Asynchronous ingestion workflow

### Objective

Connect the existing video and telemetry pipeline to the product workflow.

### Work

- Add video upload and metadata inspection.
- Add deterministic frame extraction.
- Parse DJI SRT telemetry.
- Associate frames with telemetry.
- Support local and georeferenced modes.
- Generate `geo.txt`, manifests, and SHA-256 hashes.
- Run preflight validation.
- Queue preparation in a worker instead of blocking HTTP requests.

### Exit gate

A video-only and video-plus-SRT workflow produces a valid, reproducible task
input and a complete preparation manifest.

## Phase 5 — WebODM orchestration and recovery

### Objective

Submit and monitor reconstruction tasks safely.

### Work

- Submit prepared inputs through the adapter.
- Persist the WebODM task ID on the Run.
- Poll and normalize processing progress.
- Support cancel, retry, and restart reconciliation.
- Preserve failed, cancelled, and partial Runs.
- Map WebODM task states to Astrakriti3D lifecycle states.

### Exit gate

Worker interruption, WebODM unavailability, duplicate requests, and failed
processing produce recoverable Runs with actionable status.

## Phase 6 — Astrakriti3D dashboard

### Objective

Give users one clear place to manage reconstructions.

### Work

- Add New Reconstruction action.
- Show recent Runs and R1/R2/R3 labels.
- Show processing progress and warnings.
- Show frame and telemetry counts.
- Show artifact availability.
- Add links to map, 3D model, reports, and downloads.
- Add loading, empty, error, and recovery states.

### Exit gate

A user can find, understand, and open every Mission and Run from the dashboard.

## Phase 7 — Astrakriti3D branding and visual system

### Objective

Replace the normal user-facing WebODM experience with Astrakriti3D.

### Work

- Update product name, title, logo, favicon, metadata, and navigation.
- Remove upstream product branding from normal user-facing surfaces.
- Preserve required legal attribution.
- Create reusable tokens for color, typography, spacing, panels, buttons,
  statuses, warnings, and evidence states.
- Apply the visual system consistently across dashboard, map, and 3D views.

### Exit gate

Normal users see a consistent Astrakriti3D identity throughout the workflow.

## Phase 8 — Map workspace

### Objective

Provide a branded geospatial review workspace while retaining the proven map
engine.

### Work

- Add Astrakriti3D header and breadcrumbs.
- Add orthophoto, DSM, DTM, camera, route, and frame layers.
- Add telemetry details and GeoJSON overlays.
- Add opacity controls and map measurements.
- Add open-frame, report, and download actions.

### Exit gate

Known camera and telemetry coordinates align correctly with the map layers.

## Phase 9 — 3D workspace

### Objective

Provide a branded 3D review workspace without changing viewer behavior.

### Work

- Retain the existing Potree assets and viewer logic.
- Add cameras, point-cloud, textured-model, metadata, and evidence panels.
- Restyle navigation, appearance, scene tree, measurements, and clipping tools.
- Support point, distance, height, angle, area, volume, azimuth, circle,
  height profile, annotation, and clipping measurements.
- Add report and download actions.

### Exit gate

Real point-cloud and textured-model assets load, and measurements match the
untouched viewer before and after customization.

## Phase 10 — Reports and evidence

### Objective

Make every reconstruction result explainable and auditable.

### Work

- Create browser report views.
- Generate PDF reports.
- Include input hashes, frames, telemetry, CRS, route, settings, timings,
  artifacts, measurements, limitations, and attribution.
- Implement `Verified`, `Warning`, `Unknown`, and `Unverified` evidence states.
- Prevent processing success from implying measurement or accuracy validation.

### Exit gate

Report values match the Run manifest and validation state is explicit.

## Phase 11 — SIH download center

### Objective

Create a reliable, validated delivery package.

### Work

- Collect eligible orthophoto, DSM/DTM, point cloud, mesh, textures, route,
  `geo.txt`, reports, and manifests.
- Check required files.
- Check existence and openability.
- Calculate and verify SHA-256 hashes.
- Generate the manifest.
- Create the final package only after validation succeeds.
- Hide or disable failed and missing artifacts.

### Exit gate

Every advertised file exists, opens independently, and appears in the verified
manifest.

## Phase 12 — Failure handling and quality states

### Objective

Make failures understandable and recoverable.

### Work

Handle:

- Missing or invalid SRT
- Unmatched frames
- WebODM or worker unavailability
- Out-of-memory failures
- Missing artifacts
- Hash mismatches
- Partial and cancelled tasks

For every failure, show the failed stage, preserved outputs, limitation, and
next action. Never silently delete prior Runs.

### Exit gate

Every supported failure mode has a tested, actionable UI state.

## Phase 13 — Verification and release

### Objective

Verify the integrated application and prepare a reproducible release.

### Work

- Run the existing Python tests.
- Add adapter, integration, API, worker, and browser smoke tests.
- Test local and georeferenced reconstruction.
- Test R1/R2/R3 labels, map, 3D viewer, measurements, reports, downloads,
  recovery, and responsive layouts.
- Record migration notes and upstream update procedures.
- Package configuration, branding, Docker instructions, test report, and
  license/attribution records.

### Exit gate

The complete workflow passes verification without modifying or deleting the
protected baseline until its replacement is accepted.

## Immediate next slice

The code-level integration and additive reconciliation path are now in place.
The next slice is the live gate: start the pinned WebODM stack, apply the
`0053`–`0056` migrations, preview/apply reconciliation against authorized
legacy sources, and run the real completed-Task Map/Potree/measurement and
browser acceptance suite. The workflow remains incomplete until that evidence
exists.

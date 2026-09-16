# Astrakriti3D — Phase-by-Phase Implementation Plan

Version 1.1 · 10 September 2026
Status: execution plan; every phase must pass its gate before the next phase is accepted.

## Project outcome

Astrakriti3D accepts one drone video and its matching SRT, extracts traceable frames, associates telemetry, writes metadata WebODM consumes, runs WebODM in the background through its API, collects the reconstruction, and provides a browser workspace with a 3D viewer, measurements, flight-path map, exports and PDF reporting.

WebODM supplies the reconstruction engine. Astrakriti3D owns video/SRT preparation, orchestration, viewer integration, reporting and validation.

SIH targets: georeferenced 3D mesh/point cloud, entire visible scene, spatial accuracy at most 1 m and less than 15 minutes for a 10-minute recording. Accuracy statistic, reference data, timing boundary and required output combinations must be confirmed with the organizer.

## Phase 0 — project setup and evidence

Deliver setup documentation, pinned dependencies, WebODM instructions, an environment manifest, a requirement matrix and a runtime-data directory.

Tasks:

- Confirm actual CPU, GPU, RAM, disk, operating system and container limits.
- Obtain the successful three-minute 4K video, matching SRT, extracted-image count, WebODM options, logs, outputs and report.
- Record WebODM and processing-engine versions.
- Preserve upstream licenses and attribution.
- Map each SIH requirement to an implementation, test and evidence artifact.

Gate: a clean environment can be prepared and all baseline facts are known or explicitly pending.

Execution model: phases are grouped into parallel waves. The engine track and frontend/experience track may proceed together using fixtures; a phase gate still applies before its result is used in the final benchmark.

| Wave | Engine track | Frontend/experience track |
|---|---|---|
| 1: Foundation | Phase 0 and Phase 1 | Start the application shell and load a known WebODM fixture |
| 2: Ingestion | Phases 2–4 | Upload/progress states and SRT flight-path preview |
| 3: Workspace | Phase 5 and early export smoke tests | Real point cloud, mesh, map and measurement integration |
| 4: Feasibility | Phases 6, 7 and 11 | Final workflow, evidence panel and rehearsal |

## Phase 1 — WebODM background API

Goal: control WebODM without relying on its webpage being open.

Implement:

- Background WebODM installation and health check.
- Authentication and configuration.
- Project/task creation.
- Image upload and options.
- Status/progress polling.
- Cancellation and error capture.
- Result download and hashing.
- Remote-task persistence and restart reconciliation.

Test with a small real image fixture. A worker restart must find the existing remote task before retrying.

Running command:
    python scripts/smoke_webodm.py

Gate: the command creates a real task, observes progress, collects an artifact and exits with a structured success/failure result.

## Phase 2 — video and deterministic frames

Goal: produce traceable images.

Implement FFmpeg/ffprobe inspection of duration, dimensions, codec, rotation and presentation timestamps. Extract frames while preserving source timestamps. Create a manifest containing image name, source timestamp, frame index, dimensions, transformations and SHA-256 hash.

Start with the sampling behavior that reproduces the accepted baseline. Validate decimation early against the baseline, but do not assume that a fixed frame count, one FPS or a GPS-distance threshold preserves coverage. The first speed experiment must measure whether selection changes the slow stage; frame reduction is not automatically the bottleneck.

Tests: timestamps are monotonic and within the recording; transformations are recorded; every output image maps back to the source video.

Running command:
    python run_astrakriti.py prepare --video input.mp4 --output prepared/

Gate: real video produces valid images and a complete manifest.

## Phase 3 — SRT parser and association

Goal: make the SRT usable for each frame.

Parse the actual drone SRT format and identify timestamp basis, coordinate order, hemisphere, altitude meaning, heading and missing records. Associate each selected frame with the nearest valid telemetry observation under a documented time tolerance. Record telemetry time and difference.

Do not fabricate positions across gaps. Distinguish relative altitude from absolute elevation and drone heading from camera/gimbal orientation. Preserve the original SRT.

Tests: actual SRT fixture parses; offsets are explicit; malformed or unsupported schemas give actionable errors; known frames map to expected records.

Running command:
    python run_astrakriti.py inspect-metadata --video input.mp4 --srt input.srt --output metadata/

Gate: a readable telemetry report and frame-to-SRT manifest are generated.

## Phase 4 — geolocation preparation

Goal: prove WebODM consumes SRT-derived locations.

Test one authoritative route:

1. Write GPS into selected-image EXIF and read it back; or
2. Generate an ODM-compatible image geolocation file and verify API submission.

Never submit conflicting coordinate sources. Confirm consumed locations through logs, task metadata or camera/path output. Uploading an SRT beside images is not sufficient.

Gate: a prepared-image WebODM task completes with verified camera locations and matching telemetry.

## Phase 5 — baseline reconstruction

Goal: preserve the accepted quality before optimizing.

Reproduce the accepted task and record input image count/resolution, engine version, effective options, stage timings, point cloud, mesh, map layers, camera data, viewer assets and PDF behavior. Open outputs independently.

Running command:
    python run_astrakriti.py reconstruct --video input.mp4 --srt input.srt --output runs/baseline/

Also perform early smoke tests of OBJ, PLY, LAS, GeoTIFF, GLB/GLTF and FBX handling as soon as a real artifact exists. Test axis, texture, unit and CRS preservation before the final export phase.

Gate: the accepted result is reproducibly collected, opened and documented. Do not change processing settings before this gate.

## Phase 6 — frame selection and AI

Research question: can learned input assessment improve reconstruction usefulness or total cost without unacceptable coverage loss?

Compare:

- R0: native accepted WebODM workflow, including the 200-frame approximately 18-minute observation.
- R1: deterministic prepared images.
- R2: classical blur, duplicate, overlap and coverage assessment.
- R3: R2 plus one pretrained learned signal relevant to reconstructible observations.

Use equal-frame/resolution comparisons and equal-inclusive-time comparisons. Count decoding, inference and duplicated work. Check model license, task suitability and runtime. Preserve frames that uniquely observe useful structure.

Make R2, the fast classical selector, the production candidate. Treat R3 as an optional experiment. Telemetry spacing, overlap and feature thresholds must be measured; they are not universal formulas or guarantees. Promote AI only with repeatable benefit within predeclared geometry and coverage tolerances. If it does not help, record the result and retain R2.

Gate: a measured contribution exists, or the AI requirement is explicitly marked unresolved.

## Phase 7 — accuracy and completeness

Evaluate internal shape, relative dimensions and absolute geographic position separately.

Use independent surveyed checkpoints, physical dimensions and a reference surface where available. Keep control and evaluation data separate. Record reference uncertainty, coordinate system and vertical datum.

Report the organizer-defined statistic when clarified. Until then report named horizontal, vertical and 3D measures with median, RMSE, P95, maximum and sample count where available. Do not claim a one-metre pass without applicable evidence.

For completeness, freeze visible regions before comparison. Use fixed visibility/distance rules and area-based sampling when a reference surface exists. Otherwise use labelled source-view audits. Include holes and disconnected regions, distinguishing observed-but-missing surfaces from never-observed surfaces.

Gate: accuracy and completeness are measured, or clearly marked unverified with the reason.

## Phase 8 — viewer and measurements

Load actual WebODM point-cloud, mesh, camera and coordinate artifacts into Astrakriti3D.

Integrate:

- Point-cloud and textured-model viewing.
- Camera/source-image inspection.
- Point coordinates.
- Distance, height and angle.
- Supported area tools.
- Annotations and saved measurements.
- Clipping, appearance and point-budget controls.
- Model statistics and downloads.

Measurement compatibility test:

1. Open one artifact in WebODM.
2. Select fixed points and record results.
3. Select the same model coordinates in Astrakriti3D.
4. Compare within a declared tolerance.
5. Reload the saved measurement.

The same artifact, units, coordinate transformation and measurement definition must be used. Viewer agreement proves integration consistency, not real-world accuracy. Unknown scale must not be labelled in metres.

This phase starts in Wave 1 with fixture assets so frontend integration risks are discovered early; real WebODM assets replace fixtures after Phase 5.

Gate: real assets load, measurements agree and saved measurements survive reload.

## Phase 9 — flight-path map

Create an SRT-derived flight path and frame-marker layer during preparation. After reconstruction, add WebODM camera/path data, model bounds, geographic extent, orthophoto where available and measurement locations.

Synchronize map and viewer: selecting a camera moves the 3D view and source image; selecting a model point displays its coordinates on the map.

An uploaded SRT gives a processed flight-path preview. Live aircraft tracking requires live telemetry and is outside this release.

Gate: known test coordinates and camera positions align correctly, including after reload and without a basemap network connection.

## Phase 10 — PDF and exports

Generate a downloadable Astrakriti3D PDF containing input hashes, frame/timestamp data, telemetry synchronization, WebODM version/options, stage and inclusive timings, flight-path map, model preview, outputs, CRS/scale status, measurements, accuracy/completeness status, AI comparison, limitations and attribution. Preserve a WebODM report when the installed API provides one.

Validate OBJ, PLY, LAS, GeoTIFF, GLB/GLTF and FBX. Reopen every file independently and check geometry, textures, axes, units, scale, CRS, raster extent and material links. Include conversion and validation time.

GLB/FBX conversion is smoke-tested in Phase 5 and completed here. Gate: required artifacts and the PDF open independently and match the output manifest.

## Phase 11 — performance and scalability

Measure validation/transfer, decoding, selection/AI, queue delay, feature extraction/matching, camera recovery, dense reconstruction, meshing/texturing, raster generation, export/validation and first usable viewer state.

Record inclusive wall time, CPU/GPU use, peak RAM/VRAM, disk use, container limits and cache state. Profile the successful 200-frame run before changing frame count or settings. Change one factor at a time; no fixed frame count or processing flag guarantees the target.

Begin stage profiling in Phase 5 and continue here. Test the actual ten-minute input on declared hardware with fresh data and no cached reconstruction. Test increasing workload sizes and document supported limits. Do not use fast-orthophoto or a sparse preview as evidence of a completed 3D result.

Gate: a fresh run completes the agreed output contract in strictly under 900 seconds, or the timing requirement is honestly recorded as unmet.

## Phase 12 — final integration and rehearsal

Connect upload, preparation, API processing, viewer, map, measurements, PDF, exports and recovery.

Test worker interruption, duplicate-submission prevention, cancellation, service outage, insufficient disk and memory failure. Run the command-line and browser workflows from the same processing logic.

Final rehearsal starts with an untouched recording, frozen settings and no cached geometry. Record every result, failure and timing. Produce a requirement report marking implemented, passed, failed, unverified or deferred.

## Scope and ownership

Astrakriti3D owns video/SRT ingestion, timestamping, telemetry association, geolocation preparation, frame selection/AI experiments, WebODM orchestration, job recovery, coordinate-preserving viewer/map integration, measurements, PDF reporting, exports and validation.

WebODM and dependencies retain credit for reconstruction, viewer, maps, libraries and pretrained models. Preserve license notices.

Outside this release: additional reconstruction engines, generative completion, automatic CAD, universal vendor-log support and live aircraft tracking.

## First action

Obtain the successful WebODM task’s source video, matching SRT, extracted images, effective options, logs, output assets and report. Complete Phases 0 and 1 before modifying the reconstruction pipeline.

## References

- https://github.com/WebODM/WebODM
- https://docs.webodm.org/architecture/
- https://docs.webodm.org/api/quickstart/
- https://docs.opendronemap.org/geo/
- https://docs.webodm.org/tutorials/potree-3d-viewer/
- C:/Users/Yashwanth/Downloads/SIH26158.pdf



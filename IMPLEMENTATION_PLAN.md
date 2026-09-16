# Astrakriti3D — Implementation Plan

Version 1.0 · 10 September 2026  
Status: planned; implementation and benchmark validation have not started.

## 1. Objective

Build a complete application that converts one drone recording and its associated telemetry into a georeferenced 3D scene for surveying, infrastructure inspection and disaster assessment.

Astrakriti3D accepts a drone video and SRT metadata, extracts and selects frames, synchronizes frames with telemetry, provides metadata in a format WebODM actually consumes, runs WebODM in the background through its API, collects and validates reconstruction outputs, and provides a browser viewer with measurements, maps, exports and a PDF report.

The project uses WebODM as the reconstruction engine while owning the complete video-to-result workflow.

## 2. Requirements

The supplied SIH problem statement specifies 1080p/4K video from a moving UAV on one flight path; GPS coordinates and flight metadata; optional IMU, barometric altitude, camera intrinsics and RTK/PPK; a georeferenced metrically accurate 3D mesh or point cloud; processing in less than 15 minutes for a 10-minute video; spatial accuracy of at most 1 m; the entire visible scene; OBJ, PLY, LAS, GeoTIFF, GLB/GLTF and FBX outputs; and web or desktop inspection.

Scoring weights are accuracy 30%, completeness 20%, speed 20%, innovation 15%, scalability 10% and interface 5%.

The exact accuracy statistic, reference data, timing boundary, hardware and output combinations must be clarified with the organizer. Until clarified, the system reports assumptions instead of presenting them as official rules.

## 3. End-to-end workflow

```text
Video + SRT
    ↓
Input validation
    ↓
Timestamped frame extraction
    ↓
Frame-to-SRT association
    ↓
GPS metadata written to images or supported geo file
    ↓
Prepared images submitted through WebODM API
    ↓
WebODM background reconstruction
    ↓
Output collection and coordinate validation
    ↓
Astrakriti3D viewer, map, measurements and exports
    ↓
PDF report
```

The SRT is not assumed to be consumed automatically by WebODM. Astrakriti3D performs the association and conversion first. GPS supports geographic alignment and scale; it does not by itself establish model accuracy.

## 4. System architecture

```text
Astrakriti3D frontend
        ↓
Astrakriti3D backend and worker
        ├── video/SRT preparation
        ├── frame selection and AI experiment
        ├── WebODM API adapter
        ├── output/PDF generation
        └── job and measurement records
                ↓
       WebODM services running in background
                ↓
       reconstruction engine and artifacts
```

Use React/TypeScript, Python/FastAPI, a separate worker, SQLite/local artifacts, FFmpeg/ffprobe, OpenCV, an SRT parser, a verified metadata writer, the installed WebODM service, a compatible Potree point-cloud viewer, a textured-mesh loader and a map component after CRS handling is verified.

WebODM runs as a background service. Its web page does not need to be open while Astrakriti3D submits and monitors tasks. The backend keeps credentials private and WebODM owns reconstruction scheduling.

The same processing logic is exposed by the browser and:

```text
python run_astrakriti.py --video input.mp4 --srt input.srt --output results/
```

This command is an intended deliverable.

## 5. Video and SRT preparation

Validate video duration, dimensions, codec, rotation and presentation timestamps. Parse the actual SRT time basis, coordinate fields, coordinate order, hemisphere, altitude meaning and missing records. Preserve original files.

Extract frames with their original timestamps and record filenames, image transformations and selection reasons. Start with deterministic sampling to reproduce the accepted baseline before testing quality/coverage selection.

Associate each selected frame with the closest valid SRT record under a documented time tolerance. Record the telemetry timestamp and difference. Do not fabricate positions across unresolved gaps. Distinguish relative altitude from absolute elevation and drone heading from camera/gimbal orientation.

Make WebODM consume the metadata through one authoritative route:

1. Write GPS into each selected image's EXIF metadata and read it back; or
2. Generate an ODM-compatible image geolocation file and verify its API submission.

Confirm through logs or engine metadata that coordinates were consumed. Uploading an SRT beside images is not sufficient.

Preparation produces selected images, a frame-to-telemetry manifest, metadata read-back report, source/output hashes and effective configuration.

## 6. AI and frame selection

Research question:

> Can learned input assessment improve reconstruction usefulness or total processing cost without unacceptable loss of visible-scene coverage?

Compare:

- R0: accepted WebODM workflow, including the 200-frame, approximately 18-minute baseline.
- R1: deterministic prepared images.
- R2: classical assessment using blur, duplicates, overlap and coverage.
- R3: R2 plus one pretrained learned signal relevant to reconstructible observations.

A perceptual-quality model may be a supporting signal, but visual quality alone cannot certify geometry. Choose one model only after checking task suitability, checkpoint license, runtime and compatibility. Do not claim new model training unless valid data and evaluation exist.

Use equal-frame/resolution comparisons to isolate selection effects and equal-inclusive-time comparisons to evaluate the complete product. Count decoding, inference and duplicated processing. Preserve a frame that uniquely observes useful structure even if its aesthetic score is lower.

Promote the learned component only after repeatable benefit within predeclared geometry and coverage tolerances. If it does not help, record the experiment and retain the classical baseline.

## 7. WebODM API and job management

First reproduce the successful task and record WebODM/engine versions, effective options, input image count/resolution, task ID, logs, stage timings, outputs, viewer assets and PDF-report behavior.

Implement task creation, image upload, options, remote-ID persistence, progress polling, stage logs, cancellation, bounded retries, restart reconciliation, output collection and artifact validation.

Job states:

```text
received → validating → preparing → submitted → running
         → collecting → validating outputs → completed
```

Failed and cancelled jobs retain diagnostics. Completion requires requested outputs to pass checks, not merely a successful remote status.

## 8. Viewer integration

Use WebODM/Potree capabilities as the 3D rendering foundation while integrating them into the Astrakriti3D application.

Load the actual point cloud, textured mesh, camera positions, source-image references, model bounds, coordinate transforms and geographic output layers.

Support:

- point-cloud and textured-model viewing;
- camera/source-image inspection;
- point coordinates;
- distance, height and angle measurements;
- supported area measurements;
- annotations and saved measurements;
- clipping;
- appearance and point-budget controls;
- model statistics;
- downloads.

Inventory the exact installed WebODM viewer tools and test each one. The API does not automatically bring frontend controls into Astrakriti3D; each capability is integrated explicitly.

## 9. Flight path and map

Create an SRT-derived flight path and frame-marker layer during preparation. After processing, use WebODM camera/path and geographic outputs for the result map.

Display the flight line, camera/selected-frame markers, model bounds, reconstructed extent, orthophoto where available and measurement locations. Synchronize map and viewer: selecting a camera moves the 3D view and source image; selecting a model point displays its coordinates on the map.

An uploaded SRT provides a processed flight-path preview, not live aircraft tracking. True live tracking requires live telemetry.

Preserve CRS, units, origin and reversible display transformations. A basemap is an external display layer; offline 3D inspection must remain usable.

## 10. Measurements

When the user activates a tool, the viewer returns model coordinates and Astrakriti3D applies the documented geometric calculation. For two points:

```text
distance = sqrt((x2-x1)^2 + (y2-y1)^2 + (z2-z1)^2)
```

Astrakriti3D should match WebODM when both use the same artifact, coordinates, units, display transformation and measurement definition.

Test fixed points in both viewers, compare results within a declared tolerance, reload saved measurements and compare against independent physical references. Viewer agreement proves integration consistency; it does not prove real-world accuracy. Unknown scale must not be labelled in metres.

## 11. PDF report

Test whether the installed WebODM task API provides its report. Preserve it as an upstream artifact when available.

Generate an Astrakriti3D PDF containing project/input details, video/SRT hashes, frame counts/timestamps, telemetry synchronization, WebODM version/options, stage and inclusive timings, output inventory/hashes, CRS/units/scale status, flight-path map, model preview, saved measurements, accuracy/completeness status, AI comparison, known limitations and attribution.

Reports from previous runs must be labelled during demonstrations.

## 12. Outputs and exports

Validate every required format:

- OBJ: mesh, material file and textures reopen together.
- PLY: representation, coordinates, units and colors preserved.
- LAS: coordinate scale/offset and CRS checked.
- GeoTIFF: actual raster, CRS, pixel size and extent checked.
- GLB/GLTF: geometry, axes, textures and metric scale preserved.
- FBX: supported exporter and independent reopen test.

Include conversion and validation in timing. Keep analytical assets separate from display copies and preserve transformation sidecars when needed.

## 13. Accuracy and completeness

Evaluate internal shape, relative dimensions and absolute geographic position separately. Use independent surveyed checkpoints, physical dimensions and a reference surface where available. Keep control data separate from evaluation data and record reference uncertainty, coordinate system and vertical datum.

Until the organizer clarifies the official statistic, report named horizontal, vertical and 3D measures with median, RMSE, P95, maximum and sample count where available. Do not claim a ≤1 m pass without applicable evidence.

For completeness, freeze representative visible regions before comparison. With a reference surface, use fixed visibility/distance rules and area-based sampling; otherwise use labelled source-view audits. Include holes and disconnected regions, and distinguish observed-but-missing surfaces from never-observed surfaces.

Evaluate limited angles, occlusion, blur/compression, illumination/shadows, dynamic objects, weak texture and GPS gaps as separate conditions. Preserve source observations and disclose exclusions. Do not present inferred unseen surfaces as measured geometry.

## 14. Performance and scalability

The timing target is strictly less than 900 seconds for a 600-second recording. The 18-minute/200-frame result is a baseline observation, not a bottleneck diagnosis or forecast.

Measure validation/transfer, decoding, frame selection/AI, queue delay, feature extraction/matching, camera recovery, dense reconstruction, meshing/texturing, raster generation, export conversion, validation and first usable viewer state. Record inclusive wall time, CPU/GPU use, peak RAM/VRAM, disk use, container limits and cache state.

Profile the successful task before changing frame count or settings. Change one factor at a time and retain changes only when geometry and coverage remain acceptable. No fixed frame count, GPS gate, neighbor count or feature-quality flag guarantees the target.

Test representative workload sizes, document the supported operating envelope and retain diagnostics for resource exhaustion. Begin with one active heavy job.

## 15. Validation and implementation sequence

| Milestone | Deliverable | Exit condition |
|---|---|---|
| M0: baseline | Successful task, video/SRT, settings, logs, outputs and hardware inventory | Baseline reproducible |
| M1: API runner | Background submission, status, cancellation and collection | Real task completes through runner |
| M2: input adapter | Timestamped frames, SRT association and verified geolocation | Engine consumes metadata |
| M3: viewer/map | Real model, flight path, map and measurement compatibility | Same artifact works in both viewers |
| M4: feasibility | Stage profile, accuracy/completeness checks and runtime | Processing decision made |
| M5: AI | R0–R3 comparisons | Measured contribution or unresolved status |
| M6: application | Upload-to-result workflow, PDF, exports and recovery | End-to-end test passes |
| M7: rehearsal | Untouched input, frozen configuration and evidence package | Requirement report completed |

Start references and viewer/export smoke tests at M0. Cut optional enhancements before cutting validation.

## 16. Scope and ownership

Astrakriti3D owns video/SRT ingestion, timestamping, telemetry association, supported geolocation preparation, frame-selection/AI experiments, WebODM orchestration, job recovery, coordinate-preserving viewer/map integration, PDF reporting, measurements and validation.

WebODM and dependencies retain credit for reconstruction, viewer, maps, libraries and pretrained models. Preserve license notices and document the upstream boundary.

Outside this release: additional reconstruction engines, generative completion, automatic CAD, universal vendor-log support and live aircraft tracking.

## 17. Evidence package

Deliver setup instructions, pinned versions, one-command runner, supported input documentation, manifests, WebODM configuration, timings, accuracy/completeness report, AI comparisons, viewer/map/measurement compatibility results, validated exports, PDF report, known limitations, requirement status and dependency notices.

Each requirement is labelled implemented, passed, failed, unverified or deferred and linked to a specific input, configuration and output.

## 18. References

- [WebODM repository](https://github.com/WebODM/WebODM)
- [WebODM architecture](https://docs.webodm.org/architecture/)
- [WebODM API](https://docs.webodm.org/api/quickstart/)
- [ODM image geolocation](https://docs.opendronemap.org/geo/)
- [WebODM 3D viewer](https://docs.webodm.org/tutorials/potree-3d-viewer/)
- [SIH26158.pdf](C:/Users/Yashwanth/Downloads/SIH26158.pdf)

Immediate first action: obtain the successful WebODM task's video, matching SRT, settings, logs and output assets.

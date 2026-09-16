# Production baseline

## R1 is the official default

R1 is the frozen production workflow for the DJI dataset. It uses the existing deterministic 1 FPS candidate set: the first decoded frame at or after each one-second boundary, extracted with FFmpeg seek mode. R1 contains 194 ordered JPEG frames from `inputs/DJI_0142.MP4` and uses the complete matched telemetry association and `EPSG:4326` `geo.txt`.

## Preparation provenance modes

The CLI supports two explicit modes:

```powershell
python run_astrakriti.py prepare --mode local --video inputs\DJI_0142.MP4 --output runs\local
python run_astrakriti.py prepare --mode georeferenced --video inputs\DJI_0142.MP4 --srt inputs\DJI_0142.SRT --output runs\georeferenced
```

`local` requires only video. It omits `geo.txt` and telemetry, marks the manifest `mode: local`, and reports absolute position, CRS, GPS residuals, and geographic orientation as unavailable. `georeferenced` requires a valid SRT, complete frame associations, valid coordinates, and an EPSG:4326 `geo.txt`. If `--mode` is omitted, local mode is selected. A local WebODM submission must omit geo.txt/GCP inputs; a georeferenced submission may include the generated geo.txt. A fresh output directory is required when prior geographic files exist, preventing stale telemetry reuse.

### Final video-only local workflow

SRT/GPS is optional. A video-only input follows local mode and produces point cloud, mesh, textures, orthophoto/report artifacts, and the WebODM evidence logs. It does not provide absolute geographic position, CRS, GPS residuals, or geographic orientation. Local model orientation and scale are arbitrary reconstruction coordinates and must not be interpreted as geographic truth.

There is no `python run_astrakriti.py run` command in the current CLI. The supported workflow is the following three-command sequence:

```powershell
python run_astrakriti.py preflight --mode local --video "C:\path\to\video.mp4" --output "runs\local\preflight"
python run_astrakriti.py prepare --mode local --video "C:\path\to\video.mp4" --output "runs\local"
python run_astrakriti.py reconstruct --mode local --video "C:\path\to\video.mp4" --images "runs\local\frames" --output "runs\local\webodm"
```

The completed `runs/images-r1-local-20260916` workflow is **PASS WITH WARNINGS**. Its artifacts are valid, but `frame_000001.jpg`, `frame_000002.jpg`, and `frame_000003.jpg` were not registered, and the orthophoto preview contains visible gaps. This local result must not be used to infer geographic accuracy or orientation. The detailed QA and registration investigations are preserved beside the run. R1 remains unchanged.

Run the read-only production gate before either workflow:

```powershell
python run_astrakriti.py preflight --mode local --video inputs\DJI_0142.MP4 --output runs\preflight-local
python run_astrakriti.py preflight --mode georeferenced --video inputs\DJI_0142.MP4 --srt inputs\DJI_0142.SRT --output runs\preflight-georeferenced
```

The command writes `preflight.json` and `preflight.md`, authenticates and reads WebODM health endpoints, but never submits a task. Exit code 0 is emitted only for PASS. Local mode must pass without SRT; georeferenced mode fails clearly for missing or malformed SRT, incomplete associations, invalid GPS, stale geographic outputs, or unavailable NodeODM.

After a PASS, reconstruction runs are isolated and recoverable:

```powershell
python run_astrakriti.py reconstruct --mode local --video inputs\DJI_0142.MP4 --images runs\local\frames --output evidence\reconstructions
python run_astrakriti.py reconstruct --mode georeferenced --video inputs\DJI_0142.MP4 --srt inputs\DJI_0142.SRT --images runs\georeferenced\images --geo-txt runs\georeferenced\geo.txt --output evidence\reconstructions
```

The recovery layer creates a unique run directory before submission, records hashes, mode, selector configuration, task/stage transitions, API and processing logs, artifacts, and actionable failure reports. It returns nonzero for preflight failure, service failure, cancellation, incomplete output, or reconstruction failure. It does not modify R1 or delete prior run evidence.

The machine-readable contract is [config/r1_baseline.json](../config/r1_baseline.json). Validate it with:

```powershell
python scripts/validate_r1_baseline.py
```

The validator checks source and evidence hashes, extraction settings, deterministic frame names and timestamps, image hashes and dimensions, telemetry completeness, and ordered geo records. A failure means the candidate must not be treated as R1 without an explicit baseline review.

## Frozen contract

- Extraction: 1.0-second interval, `seek` mode, FFmpeg default autorotation, source rotation `null`.
- Input: 193.5934-second DJI video; 194 frames; `frame_000001.jpg` through `frame_000194.jpg`.
- Images: 5472×3078 JPEG, FFmpeg `-q:v 2`.
- Telemetry: each frame has a matched ordered SRT association with filename, frame timestamp, telemetry timestamp, latitude, longitude, altitude, and telemetry record ID.
- Geo file: `EPSG:4326`, one line per image in `filename longitude latitude` order.
- WebODM: empty option override list, preserving the installed defaults; completed baseline task `ef1199ec-d6d3-4a3f-91c3-70f38f41de1c`.
- Expected outputs: 194 registered images, 0.921 px reprojection error, 0.373 m median GPS residual, 0.941 m P95 GPS residual, about 2.43 million point-cloud points, valid 3D/2.5D mesh, and successful textured GLB/ZIP artifacts.

The expected values are acceptance references, not permission to rewrite R1. The tolerances and provenance hashes are explicit in the JSON contract.

## Modes and change policy

R1 remains unchanged and is the production fallback. R2/classical, R3/LightGlue, adaptive, coverage-aware, and lightweight adaptive selectors are experimental modes. They must be evaluated in separate evidence directories and compared against this frozen contract; their frame-selection thresholds must not silently become R1 defaults.

Known failures include provenance mismatch, incomplete telemetry or geo records, non-deterministic extraction, interrupted/resource-starved processing, missing artifacts, and the installed native `texrecon` 2.5D access violation (`3221225477` / `0xC0000005`) observed in failed runs. Historical phase14–phase19 evidence is preserved and must not be modified.

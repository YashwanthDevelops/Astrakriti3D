# Astrakriti3D

Astrakriti3D is a reproducible drone-video 3D reconstruction project with a Python processing pipeline and a read-only local evidence dashboard.

## Project layout

- `astrakriti3d/` — Python package for preparation, selection, reconstruction, recovery, storage, and telemetry workflows.
- `run_astrakriti.py` — command-line entry point.
- `web/` — browser dashboard (`index.html`, `styles.css`, and `app.js`).
- `tests/` — automated test suite.
- `config/` and `docs/` — baseline configuration and project documentation.

## Setup

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `WEBODM_BASE_URL`, `WEBODM_USERNAME`, and `WEBODM_PASSWORD` in `.env` when using WebODM. Never commit `.env`, videos, generated evidence, credentials, or runtime databases.

## Run the dashboard

From the project root:

```powershell
python run_web.py
```

Open the local URL printed by the command in a current browser. The dashboard is read-only and serves the project evidence summary through the local API.

## Test

```powershell
python -m pytest
```

## Reconstruction workflow

R1 is the official production baseline. It is frozen at 194 DJI frames extracted at a one-second interval with deterministic FFmpeg seek mode, complete telemetry/geo provenance, and installed WebODM defaults. R2, R3, and adaptive selectors are experimental and must be compared against R1 without changing R1 or its evidence.

R1 is the official production baseline. It is frozen at 194 DJI frames extracted at a one-second interval with deterministic FFmpeg seek mode, complete telemetry/geo provenance, and the installed WebODM defaults. See [docs/PRODUCTION_BASELINE.md](docs/PRODUCTION_BASELINE.md) and [config/r1_baseline.json](config/r1_baseline.json). R2, R3, and adaptive selectors are experimental and must be compared against R1 without changing R1 or its evidence.

Preparation has two explicit provenance modes. Local mode requires only video and creates unreferenced input; georeferenced mode requires video plus valid DJI SRT telemetry and creates `geo.txt`. If `--mode` is omitted, local mode is selected. SRT is ignored in local mode.

### Video-only local reconstruction

SRT/GPS is optional. Video-only input uses `local` reconstruction mode and still produces the normal WebODM outputs: point cloud, mesh, textured model, orthophoto/report artifacts, and task logs. Without telemetry, absolute geographic position, CRS, GPS residuals, and geographic orientation are unavailable. The local model's orientation and scale are reconstruction-relative and must not be interpreted as geographic truth.

The CLI does not currently provide a single `run` subcommand. Use the supported commands sequentially:

```powershell
python run_astrakriti.py preflight --mode local --video "C:\path\to\video.mp4" --output "runs\local\preflight"
python run_astrakriti.py prepare --mode local --video "C:\path\to\video.mp4" --output "runs\local"
python run_astrakriti.py reconstruct --mode local --video "C:\path\to\video.mp4" --images "runs\local\frames" --output "runs\local\webodm"
```

The completed example in `runs/images-r1-local-20260916` is classified **PASS WITH WARNINGS**: its downloaded artifacts are valid and include point cloud, mesh, textures, orthophoto, and WebODM reports, but the first three frames were not registered and the orthophoto shows visible gaps. This result is not geographic evidence and does not change frozen R1.

```powershell
python run_astrakriti.py prepare --mode local --video inputs\DJI_0142.MP4 --output runs\local
python run_astrakriti.py prepare --mode georeferenced --video inputs\DJI_0142.MP4 --srt inputs\DJI_0142.SRT --output runs\georeferenced
```

Run the read-only production gate before preparation or WebODM submission:

```powershell
python run_astrakriti.py preflight --mode local --video inputs\DJI_0142.MP4 --output runs\preflight-local
python run_astrakriti.py preflight --mode georeferenced --video inputs\DJI_0142.MP4 --srt inputs\DJI_0142.SRT --output runs\preflight-georeferenced
```

Preflight writes `preflight.json` and `preflight.md`, checks the frozen R1 baseline, media/resources, telemetry policy, and WebODM/NodeODM health, and never submits a task. Exit code 0 is reserved for PASS.

Run one reconstruction in a new evidence directory after preflight:

```powershell
python run_astrakriti.py reconstruct --mode local --video inputs\DJI_0142.MP4 --images runs\local\frames --output evidence\reconstructions
python run_astrakriti.py reconstruct --mode georeferenced --video inputs\DJI_0142.MP4 --srt inputs\DJI_0142.SRT --images runs\georeferenced\images --geo-txt runs\georeferenced\geo.txt --output evidence\reconstructions
```

Each invocation creates a unique `run-*` directory containing `run_manifest.json`, `task_status.json`, API/processing logs, downloaded artifacts, and failure reports when applicable. Failed, cancelled, and partial runs are never reused or deleted.

This milestone provides a Python API runner for WebODM. It does not implement video/SRT processing or the frontend.

Phase 2 video preparation uses ffprobe frame presentation timestamps and selects the first decoded frame at or after each one-second boundary. This is a reproducible starting rule, not a universal frame-count or coverage guarantee. Rotation is recorded as metadata and is not silently applied.

PowerShell setup:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `WEBODM_BASE_URL`, `WEBODM_USERNAME`, and `WEBODM_PASSWORD` in the environment (or load them with your preferred local `.env` tool). Never commit `.env`. Optional settings are `WEBODM_PROJECT_NAME`, `WEBODM_REQUEST_TIMEOUT_SECONDS`, and `WEBODM_POLL_INTERVAL_SECONDS`.

Run diagnostics and tests:

```powershell
python scripts/doctor.py --output evidence/phase0/doctor.json
python -m pytest
```

Prepare a real project-local video:

```powershell
python run_astrakriti.py prepare --video input.mp4 --output prepared/
```

The command requires both `ffprobe` and `ffmpeg` on `PATH`. It writes `ffprobe.json`, `inspection.json`, `manifest.json`, `preparation_report.json`, and extracted frames under the output directory. The original video is never modified.

Run the API smoke command with at least two real project-local images:

```powershell
python scripts/smoke_webodm.py --images inputs\fixture --output runs\smoke
```

Add `--options options.json` for a JSON list of WebODM `{name, value}` pairs, or `--cancel-after 30` to exercise cancellation. Exit codes are 0 success, 2 remote/connection failure, 3 validation/configuration failure, 4 CLI validation failure, and 5 cancellation. A clean failure is expected when no real images, credentials, or reachable WebODM are configured.

## Offline Phase 6 experiment

Compare the existing 194-, 192- and 185-frame lists without starting WebODM. The runner reads local images only and writes to a new output directory.

```powershell
python scripts/run_phase6_offline.py --r1-images evidence/phase2/real-run/frames --r2-images evidence/phase6/diagnosis-followup/R2-conservative/frames --r2-exact-images evidence/phase6/r2-selection-rerun2/frames --geo-txt evidence/phase4/real-run/geo.txt --output evidence/phase6/offline-run-20260915 --threads 1
```

Use a new output directory on later runs. Add `--min-memory-bytes` to enforce a declared memory floor. This command never submits, uploads, overwrites or deletes WebODM evidence.

## Offline Phase 7 validation

Validate the preserved baseline inventory, telemetry/camera consistency and coverage proxies without starting WebODM:

```powershell
python scripts/run_phase7_offline.py --inventory evidence/phase5/baseline/baseline_inventory.json --association evidence/phase3/real-run/association_manifest.json --shots evidence/phase4/webodm-real-run/artifacts/shots.geojson --output evidence/phase7/offline-baseline-20260915
```

This reports artifact integrity and internal geolocation consistency. It intentionally leaves accuracy and surface completeness unverified until independent survey/checkpoint or reference-surface evidence is available.

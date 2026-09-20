# Phase 0 baseline and protection record

Recorded: 2026-09-16

## Protected repository

- Path: `C:\Users\Yashwanth\SIH Project\Astrakriti3D`
- Branch: `main`
- Base commit: `66bd1df Declare LightGlue resource as submodule`
- Working tree contains the documented Phase 0–4 implementation and evidence
  changes. The protected baseline commit remains identifiable as `66bd1df`;
  no existing source, evidence, run, or configuration files were deleted or
  overwritten.
- Dashboard entry point: `run_web.py`
- CLI entry point: `run_astrakriti.py`

## Local environment

| Component | Observed version | Evidence |
|---|---|---|
| Python | 3.12.0 | `python --version` |
| FFmpeg | 9.0.1-full_build-www.gyan.dev | `ffmpeg -version` |
| Docker CLI/Engine | 29.8.0 / Linux engine | `docker info`, context `desktop-linux` |
| Node.js | 26.4.0 | `node --version` |
| WebODM | 3.3.0 | Official checkout `C:\Users\Yashwanth\SIH Project\WebODM`, commit `2e26f5321e6bcccab91662c024d2c0a9bbea2d9d`; boot log |
| NodeODM | 2.3.1 (`odx` engine 3.8.3) | `docker exec node-odx-1` GET `/info`; running compose service `node-odx-1` |
| Docker engine | Operational | `docker info`, `docker ps`, and `docker run --rm hello-world` |

The official WebODM checkout is separate from Astrakriti3D and remains clean.
The Docker Compose services `webapp`, `worker`, `db`, `broker`, and `node-odx-1`
were running on context `desktop-linux`. WebODM booted as version 3.3.0,
NodeODM started on port 3000, and the real upstream fixture task completed.

## Test baseline

The full Python suite was rerun on 2026-09-16: 135 collected, 135 passed,
0 failed, 0 skipped, 0 errors (`python -m pytest -q`).

## Phase 0 exit gate

ACCEPTED/CLOSED. The protected baseline commit, branch, known working-tree
changes, entry points, tool/runtime versions, test result, source separation,
and preservation assessment are recorded. Docker, WebODM, and NodeODM runtime
evidence is now available from the accepted Phase 1–3 work.

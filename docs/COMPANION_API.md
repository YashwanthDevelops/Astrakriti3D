# Astrakriti preparation companion

The companion is a preparation-only service for the customized WebODM
application. It is not a second dashboard, login system, Project store, or
reconstruction scheduler. WebODM remains authoritative for authentication,
Project/Task identity, permissions, submission, processing, outputs, and
recovery.

## Run

Set a strong shared secret in `ASTRAKRITI_COMPANION_TOKEN`, choose a private
`ASTRAKRITI_COMPANION_ROOT`, and start:

```text
python scripts/run_companion.py
```

For a production WebODM deployment, build and run the non-root companion
container with the opt-in overlay in
`Reconstruction layer/docker-compose.astrakriti.yml`.
The overlay keeps the companion on the private Compose
network, persists preparation records in a named volume, and passes the bearer
token only to the WebODM server and companion containers. It does not publish a
host port.

In PowerShell, create a fresh random token in the current shell, change into
`Reconstruction layer`, and start the overlay:

```powershell
Set-Location "Reconstruction layer"
$env:ASTRAKRITI_COMPANION_TOKEN = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
docker compose -f docker-compose.yml -f docker-compose.build.yml -f docker-compose.astrakriti.yml up -d --build astrakriti-companion webapp
```

Keep the token in the deployment's secret store and provide it again for later
Compose operations that recreate either service. Do not commit it or place it
in browser configuration. Set `ASTRAKRITI_SOURCE_DIR` if the repository root
is not the parent `..` directory. `docker-compose.yml` remains usable without
the overlay; in that case WebODM honestly reports the
companion as `not_configured`.

The service listens on `ASTRAKRITI_COMPANION_HOST` / `ASTRAKRITI_COMPANION_PORT`
(default `127.0.0.1:5001`). The WebODM server configures the corresponding
`ASTRAKRITI_COMPANION_URL` and `ASTRAKRITI_COMPANION_TOKEN` only on the server;
neither value is sent to browser code. Set `ASTRAKRITI_COMPANION_MAX_BYTES`
to lower the default 8 GiB request limit when the deployment has a smaller
upload budget.

## Contract

Every endpoint requires `Authorization: Bearer <token>`.

- `GET /health` returns `ready` only for the preparation-only service.
- `POST /v1/preparations` accepts `job_id`, `mode` (`local` or
  `georeferenced`), a source `video`, and an SRT for georeferenced mode.
  `job_id` is the WebODM submission identity and is idempotent.
- `GET /v1/preparations/<job_id>` returns queue state, errors, and preparation
  metadata.
- `GET /v1/preparations/<job_id>/bundle` returns a ZIP only after preparation
  completes. The bundle contains the validated frame manifest, frames, and
  `geo.txt` when georeferencing produced it.
- `POST /v1/preparations/<job_id>/cancel` cancels only a queued preparation.

The service stores source inputs, queue state, and the request index under the
configured companion root. A reused identity is checked against the source
hashes and mode; it cannot silently switch to a different video/SRT. ZIP
members are path-validated before they are emitted, and the WebODM side
validates them again before copying frames into the reserved native Task.

When the URL or token is absent, WebODM reports `not_configured`; when the
service cannot be reached or fails its contract check, WebODM reports
`unavailable` or `degraded`. No successful preparation, telemetry count, or
georeference is fabricated in those states.

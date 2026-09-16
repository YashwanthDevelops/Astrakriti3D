# ADR-001: HTTP API runner with SQLite persistence

Astrakriti3D uses a small Python client around WebODM's documented REST API and SQLite for local job records. This keeps credentials in the local environment, makes worker restart reconciliation deterministic, and avoids coupling the milestone to the WebODM web UI. The client validates response shapes and treats status codes, asset names, and optional version metadata as version-dependent. No task or artifact is fabricated when prerequisites are unavailable.

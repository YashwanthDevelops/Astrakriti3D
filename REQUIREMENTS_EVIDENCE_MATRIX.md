# Phase 0/1 evidence matrix

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Reproducible setup | `pyproject.toml`, `requirements.txt`, README | install commands | implemented |
| Host diagnostics | `scripts/doctor.py` | `evidence/phase0/doctor.json` | implemented |
| JWT authentication | `astrakriti3d/client.py` | fake-server test / smoke JSON | implemented |
| Project/task submission | client + runner | `tests/test_phase1.py` | implemented |
| Polling, logs, cancellation | client + runner | tests and smoke events | implemented |
| Persistence/restart reconciliation | `storage.py`, fingerprint | persistence test | implemented |
| Artifact hash | runner | smoke JSON | implemented |
| Real reconstruction | external WebODM + real images | unavailable on current host | unverified |

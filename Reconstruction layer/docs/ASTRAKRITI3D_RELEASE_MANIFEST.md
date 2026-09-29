# ASTRAKRITI3D deployment provenance (not a release sign-off)

This manifest records the currently observed local deployment for traceability.
It is **not** a claim that the full ASTRAKRITI3D goal is complete or that the
working tree is a releasable clean commit.

## Source and image identity

| Field | Observed value |
| --- | --- |
| WebODM repository | `https://github.com/OpenDroneMap/WebODM.git` |
| Maintained branch | `codex/astrakriti3d-webodm` |
| Upstream WebODM commit at the build source | `2e26f5321e6bcccab91662c024d2c0a9bbea2d9d` (`Negate option`; `git cat-file -t` confirms this is a commit) |
| WebODM source status | Dirty working tree with modified and untracked implementation, migration, test, Docker, and documentation files. There is no clean implementation commit identifier to report. Existing changes were preserved. |
| Docker image | `webodm/webodm_webapp`, running `webapp` image ID `sha256:6743daa6a30204f484e15de7ad8a65ea2f07a5c6a14d054cb9d8fd88d3d70abe` |
| Worker image | `worker` remains on `sha256:9dd85bd1589d65b846db8e3bb6fa8945ceb66cc39d7c79deb8504dfae8b0727a`; only the `webapp` was recreated for the frontend accessibility bundle. |
| Image creation time | `2026-09-20T09:05:10.539028868Z` (current webapp image) |
| Build/deployment composition | WebODM `docker-compose.yml` plus `docker-compose.build.yml` and `docker-compose.astrakriti.yml`; the build overlay builds from this maintained source tree, and the Astrakriti overlay configures the protected preparation companion. |
| Database schema | Astrakriti app migrations `0053` through `0057` were observed applied in the running deployment. |

## Extension and ownership boundary

ASTRAKRITI3D is installed as `coreplugins/astrakriti3d`. WebODM remains the
authority for users, sessions, Projects, Task permissions and lifecycle,
native MapView/Potree, reconstruction outputs, and downloads. The plugin owns
the product shell, preparation/evidence integration, Mission metadata,
Task-scoped measurement persistence, and associated APIs. The companion is a
protected preparation service only; it does not own a second reconstruction
scheduler or Task lifecycle.

Focused model and migration patches are documented in
[`ASTRAKRITI3D_WEBODM.md`](ASTRAKRITI3D_WEBODM.md), including why plugin storage
was insufficient and the migration/reconciliation/rollback procedure. No
upstream core viewer engine or authentication system is replaced.

## Upgrade and rollback procedure

1. Before a release, make a database and media-volume backup and preserve the
   exact current image digest and source revision.
2. Rebase the focused Astrakriti plugin, model, migration, and documented
   WebODM changes onto the explicitly selected upstream WebODM commit. Review
   upstream conflicts; do not update the pin implicitly.
3. Build the WebODM and companion images from the documented Compose overlays.
   Run Django checks, migration-state checks, the applicable complete test
   suite, and the real-task viewer/measurement acceptance gate before rollout.
4. Confirm no queued/running reconstruction or pending worker operation before
   restarting app services. Apply additive migrations using the documented
   backup and reconciliation procedure; never reset production data.
5. Record the resulting clean source commit, upstream commit, image digests,
   migration inventory, test results, and live acceptance evidence in a new
   release manifest. This current manifest must not be reused as a clean release
   record.
6. For rollback, use the verified database/media backup and prior recorded
   image. Follow the data-aware rollback instructions in
   [`ASTRAKRITI3D_WEBODM.md`](ASTRAKRITI3D_WEBODM.md); do not reverse migrations
   or remove measurement/link records without the documented export/backup
   safeguards.

## Current release gate

The image and migrations are running, but this is **not releasable/sign-off
evidence**. The loopback discrepancy was resolved on 2026-09-20: `127.0.0.1`
served a separate Windows WebODM process, while `localhost` reached the
Docker-backed deployment. The authenticated in-app browser rendered the
ASTRAKRITI3D shell and accepted Task routes on `localhost`; a disposable,
original-resolution video/SRT browser submission completed a real WebODM Task
and was cleaned up. The full visual-reference comparison and page-by-page
accessibility remain incomplete. The concrete Map/Potree keyboard and naming
defects found in the earlier browser audit were corrected and rechecked on the
current webapp image; that bounded remediation is recorded in
[`ASTRAKRITI3D_LIVE_ACCEPTANCE.md`](ASTRAKRITI3D_LIVE_ACCEPTANCE.md). The bounded
New Reconstruction keyboard/semantics sample also passed.
Measurement/reload/restart/export browser replay (historical evidence is
preserved), and broad regression gates remain incomplete. See
[`ASTRAKRITI3D_LIVE_ACCEPTANCE.md`](ASTRAKRITI3D_LIVE_ACCEPTANCE.md) for the
timestamped evidence and open gates.

# Astrakriti3D integration boundary

The Astrakriti3D companion and the customized WebODM application are shipped
in one repository. The WebODM source lives in `WebODM/` and is based on the
upstream revision recorded in `WebODM/ASTRAKRITI3D_SOURCE.md`. WebODM remains
the production owner of authentication, Project/Task identity, permissions,
reconstruction lifecycle, status, cancellation, asset retrieval, and health
checks.

The preparation-only companion in `astrakriti3d.companion_api` owns video
extraction, frame selection, SRT/telemetry association, and validated
preparation bundles before native Task commit. It does not expose a dashboard,
second login, Project store, or reconstruction scheduler. Its bearer-protected
contract is documented in `docs/COMPANION_API.md`.

The existing `integrations.WebODMAdapter` and
`astrakriti3d.client.WebODMClient` remain compatibility/CLI transport layers
for retained backend tests and migration tooling. They must not compete with
the native WebODM Task lifecycle in the production shell.

Legacy `ProductStore` Mission/Run rows and `JobStore` job rows are reconciled
into WebODM's additive `AstrakritiLegacyLink` table by the WebODM
`astrakriti_reconcile` command. The command previews by default, accepts an
explicit identity map, preserves the original source payload/path, and leaves
unresolved or conflicting records marked for reconciliation rather than
guessing a Project or Task from a display name.

The customized WebODM source, its upstream license and attribution files, and
its uninitialized upstream dependencies are included in this repository. Root
`.gitmodules` records the nested WebODM dependencies so a recursive clone can
restore them.

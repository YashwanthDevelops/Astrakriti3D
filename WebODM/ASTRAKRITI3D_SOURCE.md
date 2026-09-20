# Vendored WebODM source

This directory contains the customized WebODM source used by Astrakriti3D.
It was copied from the upstream WebODM checkout at commit
`2e26f5321e6bcccab91662c024d2c0a9bbea2d9d` (upstream repository:
`https://github.com/OpenDroneMap/WebODM.git`) together with its local
Astrakriti3D changes and documentation.

The source is part of the Astrakriti3D repository; this directory is not a
nested Git repository or a Git submodule. The parent repository records the
vendored source snapshot and the Astrakriti-specific changes. The original
WebODM Git history remains available from the upstream repository. Preserve
WebODM's `LICENSE.md`, `TRADEMARK.md`, and other upstream notices when using
or redistributing this source.

WebODM's `locale` and `nodeodm/external/NodeODM` dependencies are represented
by Git submodules declared in the parent repository's `.gitmodules`. Clone the
Astrakriti3D repository with `--recurse-submodules` to fetch them.

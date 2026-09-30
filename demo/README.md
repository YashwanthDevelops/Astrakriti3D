# Astrakriti3D Field Studio demo

This is a standalone, frontend-only SIH showcase. It uses deterministic sample
values from the documented R1 baseline and local preview images. Reconstruction
replay, model measurements, and report export run in the browser; the demo does
not call the project backend or any external service.

From the repository root, serve the project locally:

```powershell
python -m http.server 4173 --bind 127.0.0.1 --directory demo
```

Open <http://127.0.0.1:4173/>. No package installation is required.

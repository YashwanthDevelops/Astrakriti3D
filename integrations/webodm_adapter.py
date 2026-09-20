"""Astrakriti3D-facing WebODM adapter.

Product services should depend on this small contract rather than on WebODM
models, URL details, or the legacy client implementation.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol


class WebODMAdapterError(RuntimeError):
    """Raised when an adapter operation cannot be completed."""


class _Client(Protocol):
    def find_or_create_project(self) -> str: ...
    def submit_task(self, project_id: str, manifest: list[Mapping[str, Any]], options: Any, geo_txt: str | None = None) -> str: ...
    def task(self, project_id: str, task_id: str) -> Mapping[str, Any]: ...
    def cancel(self, project_id: str, task_id: str) -> None: ...
    def download(self, project_id: str, task_id: str, asset: str, destination: Path) -> Path: ...


@dataclass(frozen=True)
class TaskStatus:
    task_id: str
    state: str
    progress: float | None
    raw: Mapping[str, Any]


class WebODMAdapter:
    """Stable orchestration boundary for WebODM operations."""

    def __init__(self, client: _Client):
        self._client = client

    def authenticate(self) -> None:
        """Authenticate the transport without exposing its implementation."""
        authenticate = getattr(self._client, "authenticate", None)
        if authenticate is None:
            return
        try:
            authenticate()
        except Exception as exc:
            raise WebODMAdapterError("could not authenticate with WebODM") from exc

    def create_project(self) -> str:
        return self._client.find_or_create_project()

    def create_task(self, project_id: str, manifest: Iterable[Mapping[str, Any]], options: Any, geo_txt: str | None = None) -> str:
        try:
            if geo_txt is None:
                return self._client.submit_task(project_id, list(manifest), options)
            return self._client.submit_task(project_id, list(manifest), options, geo_txt)
        except Exception as exc:
            raise WebODMAdapterError(f"could not create processing task: {exc}") from exc

    def get_task_status(self, project_id: str, task_id: str) -> TaskStatus:
        try:
            raw = self._client.task(project_id, task_id)
        except Exception as exc:
            raise WebODMAdapterError("could not read processing task status") from exc
        state = str(raw.get("status", raw.get("processingStatus", "UNKNOWN"))).upper()
        progress = raw.get("progress")
        try:
            progress = float(progress) if progress is not None else None
        except (TypeError, ValueError):
            progress = None
        return TaskStatus(str(task_id), state, progress, raw)

    def cancel_task(self, project_id: str, task_id: str) -> None:
        try:
            self._client.cancel(project_id, task_id)
        except Exception as exc:
            raise WebODMAdapterError("could not cancel processing task") from exc

    def get_output(self, project_id: str, task_id: str) -> str:
        try:
            return self._client.output(project_id, task_id)
        except Exception as exc:
            raise WebODMAdapterError("could not read processing task output") from exc

    def get_assets(self, project_id: str, task_id: str, assets: Iterable[str], destination: Path) -> list[Path]:
        results = []
        for asset in assets:
            try:
                results.append(self._client.download(project_id, task_id, asset, destination / asset))
            except Exception as exc:
                raise WebODMAdapterError(f"could not download asset: {asset}") from exc
        return results

    def health_check(self) -> bool:
        try:
            request = getattr(self._client, "request", None)
            if request is not None:
                response = request("GET", "/processingnodes/")
                body = response.json()
                nodes = body if isinstance(body, list) else body.get("results", [])
                return bool(nodes) and any(
                    node.get("online") is True or node.get("status") in ("online", 1)
                    for node in nodes
                )
            return False
        except Exception:
            return False

"""Server-side client for the optional Astrakriti preparation service.

The browser never receives the companion URL or bearer token. When the
boundary is not configured, callers get an explicit unavailable state rather
than a fabricated preparation result.
"""

import os
from pathlib import Path

import requests


class CompanionNotConfigured(RuntimeError):
    """The optional preparation service is not configured for this WebODM."""


class CompanionError(RuntimeError):
    """A safe, user-facing companion service failure."""


class AstrakritiCompanionClient:
    def __init__(self, base_url=None, token=None, timeout=None):
        self.base_url = (base_url if base_url is not None else os.environ.get("ASTRAKRITI_COMPANION_URL", "")).strip().rstrip("/")
        self.token = token if token is not None else os.environ.get("ASTRAKRITI_COMPANION_TOKEN", "")
        try:
            configured_timeout = float(timeout if timeout is not None else os.environ.get("ASTRAKRITI_COMPANION_TIMEOUT", "15"))
        except (TypeError, ValueError):
            configured_timeout = 15.0
        self.timeout = max(1.0, min(configured_timeout, 120.0))

    @property
    def configured(self):
        return bool(self.base_url and self.token)

    def _request(self, method, path, **kwargs):
        if not self.configured:
            raise CompanionNotConfigured("Astrakriti companion URL and token are not configured")
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = "Bearer " + self.token
        headers.setdefault("Accept", "application/json")
        try:
            response = requests.request(
                method,
                self.base_url + path,
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise CompanionError("Astrakriti companion could not be reached") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except (TypeError, ValueError):
                detail = None
            raise CompanionError(detail or "Astrakriti companion rejected the request")
        return response

    def health(self):
        return self._request("GET", "/health").json()

    def health_payload(self):
        if not self.base_url and not self.token:
            return {
                "status": "not_configured",
                "detail": "No protected Astrakriti preparation service is configured.",
            }
        if not self.configured:
            return {
                "status": "unavailable",
                "detail": "The companion URL and bearer token must both be configured.",
            }
        try:
            body = self.health()
        except (CompanionNotConfigured, CompanionError) as exc:
            return {"status": "unavailable", "detail": str(exc)}
        if body.get("status") != "ready" or body.get("preparation_only") is not True:
            return {
                "status": "degraded",
                "detail": "The companion responded without a ready preparation contract.",
            }
        return {
            "status": "connected",
            "detail": "Protected Astrakriti preparation service is ready.",
        }

    def start_preparation(self, job_id, mode, video, srt=None):
        files = {
            "video": (
                getattr(video, "name", "source-video"),
                video,
                getattr(video, "content_type", "application/octet-stream"),
            )
        }
        if srt is not None:
            files["srt"] = (
                getattr(srt, "name", "telemetry.srt"),
                srt,
                getattr(srt, "content_type", "text/plain"),
            )
        return self._request(
            "POST",
            "/v1/preparations",
            data={"job_id": str(job_id), "mode": mode},
            files=files,
        ).json()

    def preparation_status(self, job_id):
        return self._request("GET", "/v1/preparations/{}".format(job_id)).json()

    def download_bundle(self, job_id, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self._request(
            "GET",
            "/v1/preparations/{}/bundle".format(job_id),
            stream=True,
        )
        temporary = destination.with_suffix(destination.suffix + ".downloading")
        try:
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        handle.write(chunk)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return destination

    def cancel_preparation(self, job_id):
        return self._request(
            "POST", "/v1/preparations/{}/cancel".format(job_id)
        ).json()

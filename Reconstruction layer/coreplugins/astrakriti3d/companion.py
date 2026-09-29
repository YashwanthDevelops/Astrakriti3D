"""Server-side client for the optional Astrakriti preparation service.

The browser never receives the companion URL or bearer token. When the
boundary is not configured, callers get an explicit unavailable state rather
than a fabricated preparation result.
"""

import os
from pathlib import Path
import uuid

import requests


class _StreamingMultipartBody:
    """Encode multipart fields while reading file parts in bounded chunks."""

    _CRLF = b"\r\n"
    _CHUNK_SIZE = 1024 * 1024

    def __init__(self, fields, files):
        self.boundary = "----Astrakriti3D{}".format(uuid.uuid4().hex)
        self.parts = []
        self.closing = "--{}--\r\n".format(self.boundary).encode("ascii")
        self.consumed = False

        for name, value in fields.items():
            header = self._part_header(name)
            payload = str(value).encode("utf-8")
            self.parts.append((header, payload, len(payload)))

        for name, (filename, fileobj, content_type) in files.items():
            safe_filename = os.path.basename(str(filename).replace("\\", "/")) or "upload"
            header = self._part_header(
                name,
                filename=safe_filename,
                content_type=content_type or "application/octet-stream",
            )
            position = fileobj.tell()
            fileobj.seek(0, os.SEEK_END)
            size = fileobj.tell() - position
            fileobj.seek(position)
            self.parts.append((header, fileobj, size))

        self.length = len(self.closing) + sum(
            len(header) + size + len(self._CRLF)
            for header, _payload, size in self.parts
        )

    @staticmethod
    def _quoted_parameter(value):
        value = str(value).replace("\r", "").replace("\n", "")
        return '"{}"'.format(value.replace("\\", "\\\\").replace('"', '\\"'))

    def _part_header(self, name, filename=None, content_type=None):
        disposition = "Content-Disposition: form-data; name={}".format(
            self._quoted_parameter(name)
        )
        if filename is not None:
            disposition += "; filename={}".format(self._quoted_parameter(filename))
        lines = ["--{}".format(self.boundary), disposition]
        if content_type:
            safe_content_type = str(content_type).replace("\r", "").replace("\n", "")
            lines.append("Content-Type: {}".format(safe_content_type))
        return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")

    @property
    def content_type(self):
        return "multipart/form-data; boundary={}".format(self.boundary)

    def __len__(self):
        return self.length

    def __iter__(self):
        if self.consumed:
            raise ValueError("multipart body streams can only be consumed once")
        self.consumed = True
        for header, payload, size in self.parts:
            yield header
            if isinstance(payload, bytes):
                if payload:
                    yield payload
            else:
                remaining = size
                while remaining:
                    chunk = payload.read(min(self._CHUNK_SIZE, remaining))
                    if not chunk:
                        raise IOError("multipart source changed during upload")
                    if len(chunk) > remaining:
                        raise IOError("multipart source changed during upload")
                    remaining -= len(chunk)
                    yield chunk
            yield self._CRLF
        yield self.closing


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
                os.path.basename(str(getattr(video, "name", "source-video")).replace("\\", "/")),
                video,
                getattr(video, "content_type", "application/octet-stream"),
            )
        }
        if srt is not None:
            files["srt"] = (
                os.path.basename(str(getattr(srt, "name", "telemetry.srt")).replace("\\", "/")),
                srt,
                getattr(srt, "content_type", "text/plain"),
            )
        body = _StreamingMultipartBody(
            {"job_id": str(job_id), "mode": mode},
            files,
        )
        return self._request(
            "POST",
            "/v1/preparations",
            data=body,
            headers={
                "Content-Type": body.content_type,
                "Content-Length": str(len(body)),
            },
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

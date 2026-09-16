from dataclasses import dataclass
import os
from pathlib import Path

@dataclass(frozen=True)
class Config:
    base_url: str
    username: str
    password: str
    project_name: str = "Astrakriti3D"
    timeout: float = 30.0
    poll_interval: float = 3.0
    db_path: Path = Path("runtime/jobs.sqlite3")
    max_poll_seconds: float = 900.0
    max_unknown_polls: int = 5

    @classmethod
    def from_env(cls, env_path=None):
        env = dict(os.environ)
        ep = Path(env_path) if env_path else Path(".env")
        if not ep.is_file():
            fallback = Path(__file__).resolve().parents[1] / ".env"
            if fallback.is_file(): ep = fallback
        if ep.is_file():
            for line in ep.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line: continue
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip("'\""))
        return cls(
            env.get("WEBODM_BASE_URL", "").strip().rstrip("/"),
            env.get("WEBODM_USERNAME", "").strip(),
            env.get("WEBODM_PASSWORD", ""),
            env.get("WEBODM_PROJECT_NAME", "Astrakriti3D").strip() or "Astrakriti3D",
            float(env.get("WEBODM_REQUEST_TIMEOUT_SECONDS", "30")),
            float(env.get("WEBODM_POLL_INTERVAL_SECONDS", "3")),
            Path("runtime/jobs.sqlite3"),
            float(env.get("WEBODM_MAX_POLL_SECONDS", "3600")),
            int(env.get("WEBODM_MAX_UNKNOWN_POLLS", "5")),
        )

    def validate(self):
        missing = [k for k, v in (("WEBODM_BASE_URL", self.base_url), ("WEBODM_USERNAME", self.username), ("WEBODM_PASSWORD", self.password)) if not v]
        if missing:
            raise ValueError("Missing required configuration: " + ", ".join(missing))

"""Persistent Astrakriti3D product records and Run lifecycle."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path

RUN_STATES = {
    "CREATED", "PREFLIGHT", "PREPARING", "READY", "SUBMITTED", "PROCESSING", "COMPLETED",
    "PREFLIGHT_FAILED", "PREPARATION_FAILED", "SUBMISSION_FAILED", "PROCESSING_FAILED",
    "PARTIAL", "CANCELLED", "RECOVERY_REQUIRED",
}
TRANSITIONS = {
    "CREATED": {"PREFLIGHT", "CANCELLED"},
    "PREFLIGHT": {"PREPARING", "PREFLIGHT_FAILED", "CANCELLED"},
    "PREPARING": {"READY", "PREPARATION_FAILED", "CANCELLED"},
    "READY": {"SUBMITTED", "CANCELLED"},
    "SUBMITTED": {"PROCESSING", "SUBMISSION_FAILED", "RECOVERY_REQUIRED", "CANCELLED"},
    "PROCESSING": {"COMPLETED", "PROCESSING_FAILED", "PARTIAL", "RECOVERY_REQUIRED", "CANCELLED"},
    "RECOVERY_REQUIRED": {"SUBMITTED", "PROCESSING", "PROCESSING_FAILED", "CANCELLED"},
}

def _now():
    return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class Run:
    run_id: str
    mission_id: str
    label: str
    status: str
    webodm_task_id: str | None

class ProductStore:
    """Small SQLite repository for product lifecycle and provenance records."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS missions (mission_id TEXT PRIMARY KEY, name TEXT NOT NULL, input_video TEXT, input_srt TEXT, input_hashes TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, label TEXT NOT NULL, input_hash TEXT NOT NULL, frame_selection_policy TEXT NOT NULL, matching_policy TEXT NOT NULL, reconstruction_config TEXT NOT NULL, webodm_task_id TEXT, submission_key TEXT UNIQUE, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(mission_id, label));
            CREATE TABLE IF NOT EXISTS artifacts (artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, type TEXT NOT NULL, path TEXT NOT NULL, size INTEGER, sha256 TEXT, crs TEXT, validation_status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence (evidence_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, criterion TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL, limitations TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS run_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, from_status TEXT NOT NULL, to_status TEXT NOT NULL, created_at TEXT NOT NULL);
            """)
    def _db(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db
    def create_mission(self, mission_id, name, input_video=None, input_srt=None, input_hashes=None):
        with self._db() as db:
            db.execute("INSERT INTO missions VALUES (?,?,?,?,?,?)", (mission_id, name, input_video, input_srt, json.dumps(input_hashes or {}, sort_keys=True), _now()))
    def create_run(self, run_id, mission_id, label, input_hash, frame_selection_policy="default", matching_policy="default", reconstruction_config=None):
        with self._db() as db:
            db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (run_id, mission_id, label, input_hash, frame_selection_policy, matching_policy, json.dumps(reconstruction_config or {}, sort_keys=True), None, None, "CREATED", _now(), _now()))
    def get_run(self, run_id):
        with self._db() as db:
            row = db.execute("SELECT run_id,mission_id,label,status,webodm_task_id FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return Run(**dict(row)) if row else None
    def transition(self, run_id, target):
        if target not in RUN_STATES: raise ValueError(f"unknown Run state: {target}")
        with self._db() as db:
            row = db.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row: raise KeyError(run_id)
            current = row["status"]
            if target == current: return self.get_run(run_id)  # idempotent replay
            if target not in TRANSITIONS.get(current, set()): raise ValueError(f"invalid Run transition: {current} -> {target}")
            db.execute("UPDATE runs SET status=?,updated_at=? WHERE run_id=?", (target, _now(), run_id))
            db.execute("INSERT INTO run_events(run_id,from_status,to_status,created_at) VALUES (?,?,?,?)", (run_id, current, target, _now()))
        return self.get_run(run_id)
    def attach_webodm_task(self, run_id, task_id):
        with self._db() as db:
            current = db.execute("SELECT webodm_task_id FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not current: raise KeyError(run_id)
            if current["webodm_task_id"] not in (None, str(task_id)): raise ValueError("Run is already linked to a different WebODM task")
            db.execute("UPDATE runs SET webodm_task_id=?,updated_at=? WHERE run_id=?", (str(task_id), _now(), run_id))
        return self.get_run(run_id)
    def claim_submission(self, run_id, submission_key):
        """Atomically reserve a submission identity so retries cannot submit twice."""
        with self._db() as db:
            row = db.execute("SELECT submission_key FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row: raise KeyError(run_id)
            if row["submission_key"] not in (None, submission_key): raise ValueError("Run already has a different submission identity")
            try:
                db.execute("UPDATE runs SET submission_key=?,updated_at=? WHERE run_id=?", (submission_key, _now(), run_id))
            except sqlite3.IntegrityError as exc:
                raise ValueError("submission identity already belongs to another Run") from exc
        return self.get_run(run_id)
    def list_artifacts(self, run_id):
        with self._db() as db: return [dict(row) for row in db.execute("SELECT * FROM artifacts WHERE run_id=?", (run_id,))]
    def list_evidence(self, owner_id):
        with self._db() as db: return [dict(row) for row in db.execute("SELECT * FROM evidence WHERE owner_id=?", (owner_id,))]
    def add_artifact(self, artifact_id, run_id, type, path, size=None, sha256=None, crs=None, validation_status="UNVERIFIED"):
        with self._db() as db: db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?)", (artifact_id, run_id, type, str(path), size, sha256, crs, validation_status))
    def add_evidence(self, evidence_id, owner_id, criterion, source, status, limitations=""):
        with self._db() as db: db.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?)", (evidence_id, owner_id, criterion, source, status, limitations, _now()))

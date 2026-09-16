import hashlib, json, sqlite3
from datetime import datetime, timezone
from pathlib import Path

STATES = {"received", "validating", "submitted", "running", "collecting", "completed", "failed", "cancelled"}
def now(): return datetime.now(timezone.utc).isoformat()

class JobStore:
    def __init__(self, path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS jobs (
              local_id TEXT PRIMARY KEY, project_id TEXT, task_id TEXT, fingerprint TEXT UNIQUE,
              image_manifest TEXT NOT NULL, options TEXT NOT NULL, state TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, progress REAL,
              diagnostics TEXT, artifacts TEXT NOT NULL DEFAULT '[]', event_history TEXT NOT NULL DEFAULT '[]')""")
            cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
            if "event_history" not in cols: c.execute("ALTER TABLE jobs ADD COLUMN event_history TEXT NOT NULL DEFAULT '[]'")
    def db(self): return sqlite3.connect(self.path)
    def create(self, local_id, fingerprint, manifest, options):
        with self.db() as c:
            c.execute("INSERT INTO jobs (local_id,project_id,task_id,fingerprint,image_manifest,options,state,created_at,updated_at,progress,diagnostics,artifacts,event_history) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (local_id,None,None,fingerprint,json.dumps(manifest),json.dumps(options),"received",now(),now(),None,None,"[]","[]"))
    def get_by_fingerprint(self, fingerprint):
        with self.db() as c:
            c.row_factory = sqlite3.Row; r=c.execute("SELECT * FROM jobs WHERE fingerprint=?",(fingerprint,)).fetchone()
            return dict(r) if r else None
    def find_by_manifest(self, manifest, options):
        target={x["sha256"] for x in manifest}
        with self.db() as c:
            c.row_factory=sqlite3.Row
            for r in c.execute("SELECT * FROM jobs ORDER BY created_at DESC"):
                row=dict(r)
                try:
                    if {x["sha256"] for x in json.loads(row["image_manifest"])} == target and json.loads(row["options"]) == options:
                        return row
                except (KeyError, TypeError, json.JSONDecodeError): pass
        return None
    def get(self, local_id):
        with self.db() as c:
            c.row_factory=sqlite3.Row; r=c.execute("SELECT * FROM jobs WHERE local_id=?",(local_id,)).fetchone(); return dict(r) if r else None
    def update(self, local_id, **fields):
        fields["updated_at"] = now(); fields = {k:(json.dumps(v) if k in {"diagnostics","artifacts"} and not isinstance(v,str) else v) for k,v in fields.items()}
        with self.db() as c: c.execute("UPDATE jobs SET "+", ".join(f"{k}=?" for k in fields)+" WHERE local_id=?", (*fields.values(),local_id))
    def event(self, local_id, event):
        with self.db() as c:
            r=c.execute("SELECT event_history FROM jobs WHERE local_id=?",(local_id,)).fetchone(); history=json.loads(r[0] or "[]")
            history.append(event); c.execute("UPDATE jobs SET event_history=?, updated_at=? WHERE local_id=?",(json.dumps(history),now(),local_id))

def manifest_for_images(directory):
    p=Path(directory)
    if not p.is_dir(): raise ValueError(f"Image directory does not exist: {p}")
    files=sorted(x for x in p.iterdir() if x.is_file() and x.suffix.lower() in {".jpg",".jpeg",".png",".tif",".tiff"})
    if len(files)<2: raise ValueError("At least two image files are required")
    result=[]
    for x in files:
        data=x.read_bytes(); dimensions=None
        if data[:2] == b"\xff\xd8":
            i=2
            while i+9 < len(data):
                if data[i] != 0xff: i += 1; continue
                marker=data[i+1]; i += 2
                if marker in (0xd8,0xd9): continue
                n=int.from_bytes(data[i:i+2],"big")
                if marker in range(0xc0,0xc4): dimensions=[int.from_bytes(data[i+3:i+5],"big"),int.from_bytes(data[i+5:i+7],"big")]; break
                i += n
        result.append({"name":x.name,"path":str(x.resolve()),"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data),"dimensions":dimensions,"file_type":x.suffix.lower().lstrip('.')})
    return result

def preflight_report(manifest):
    dimensions=[m["dimensions"] for m in manifest if m.get("dimensions")]
    warnings=[]
    if len(manifest)<3: warnings.append("Only two images are present; reconstruction success is unlikely without strong overlap.")
    if not dimensions: warnings.append("Dimensions could not be parsed by the lightweight preflight.")
    return {"image_count":len(manifest),"images":manifest,"warnings":warnings,"overlap_diagnostic":"not_available_without_feature_backend"}

def fingerprint(manifest, options, geo_sha256=None):
    stable=[{k:x.get(k) for k in ("name","path","sha256","bytes")} for x in manifest]
    return hashlib.sha256(json.dumps({"images":stable,"options":options,"geo_txt_sha256":geo_sha256},sort_keys=True).encode()).hexdigest()

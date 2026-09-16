"""Generate a read-only inventory and conservative cleanup proposal."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "cleanup_audit.json"
OUT_MD = ROOT / "cleanup_audit.md"
CAT = {
    "production": "Required for production",
    "tests": "Required for tests",
    "evidence": "Required for reproducibility/evidence",
    "experimental": "Experimental but should be retained",
    "archive": "Generated artifact that can be archived",
    "cache": "Temporary/cache file that is safe to delete",
    "duplicate": "Duplicate or obsolete file",
    "unclear": "Unclear — requires human confirmation",
}
TEXT_EXT = {".py", ".md", ".json", ".txt", ".csv", ".toml", ".ini", ".cfg", ".yaml", ".yml", ".ps1", ".js", ".css", ".html", ".srt", ".log"}

def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()

def classify(path: Path):
    p, name = rel(path), path.name
    if name in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"} or path.suffix in {".pyc", ".pyo", ".tmp", ".temp"}:
        return "cache", "Python/test cache or temporary by extension/name"
    if path.is_dir() and name in {"archive", "evidence", "astrakriti3d", "config", "docs", "model-resources", "runtime", "tests", "web"}:
        directory_categories = {
            "archive": ("archive", "Existing archive root"),
            "evidence": ("evidence", "Historical evidence root"),
            "astrakriti3d": ("production", "Application source root"),
            "config": ("production", "Production configuration root"),
            "docs": ("production", "Project documentation root"),
            "model-resources": ("experimental", "Pinned experimental model resources"),
            "runtime": ("evidence", "Reproducibility state root"),
            "tests": ("tests", "Test suite root"),
            "web": ("production", "Existing web assets root"),
        }
        return directory_categories[name]
    if p.startswith("archive/"):
        if "/caches/" in p:
            return "cache", "Archived cache payload; safe to delete only after archive review"
        return "archive", "Previously archived bulky/generated payload"
    if p.startswith("evidence/"):
        return "evidence", "Historical phase report, manifest, log, artifact inventory, or source evidence"
    if p.startswith("inputs/"):
        return ("production", "Current DJI production input and telemetry source") if path.suffix.lower() in {".mp4", ".srt"} else ("tests", "Project-local image fixture/input")
    if p.startswith("model-resources/"):
        return "experimental", "Pinned model resource used by experimental R3/LightGlue selection"
    if p.startswith("tests/"):
        return "tests", "Pytest test or test fixture"
    if p.startswith("config/") or p.startswith("docs/"):
        return "production", "Production configuration or baseline documentation"
    if p.startswith("astrakriti3d/"):
        return ("experimental", "Experimental selector implementation retained for research") if any(x in name.lower() for x in ("selection", "lightglue", "coverage")) else ("production", "Imported application module")
    if p.startswith("scripts/"):
        if name == "generate_cleanup_audit.py": return "evidence", "Read-only audit reproducibility tool"
        return ("experimental", "Selector/comparison research script") if any(x in name.lower() for x in ("selection", "r2", "r3", "adaptive", "coverage", "lightweight", "aggressive")) else ("production", "Operational CLI/diagnostic script")
    if name in {"run_astrakriti.py", "run_web.py", "pyproject.toml", "requirements.txt", ".env.example", ".gitignore", "report_schema.json"}:
        return "production", "CLI, package metadata, schema, or environment template"
    if name == ".env": return "unclear", "Local credential/configuration file; requires human confirmation"
    if name in {"README.md", "ARCHITECTURE_DECISION_RECORD.md", "LICENSE_NOTES.md", "REQUIREMENTS_EVIDENCE_MATRIX.md", "IMPLEMENTATION_PLAN.md", "IMPLEMENTATION_PLAN_PHASES.md"}:
        return "evidence", "Project documentation or planning/reproducibility record"
    if p.startswith("runtime/"): return "evidence", "Local job database and reproducibility state"
    if p.startswith("web/"): return "production", "Existing project web assets"
    return "unclear", "No safe automated classification rule"

def references(files):
    texts = []
    for path in files:
        if path.suffix.lower() in TEXT_EXT and path.stat().st_size <= 20 * 1024 * 1024:
            try: texts.append((rel(path), path.read_text(encoding="utf-8", errors="ignore")))
            except OSError: pass
    out = {}
    for path in files:
        rp = rel(path); variants = {rp, rp.replace("/", "\\"), path.name}; hits = []
        for src, text in texts:
            if src != rp and any(v in text for v in variants): hits.append(src)
        out[rp] = sorted(set(hits))
    return out

def main():
    files = sorted((p for p in ROOT.rglob("*") if p.is_file() and not p.is_symlink()), key=rel)
    dirs = sorted((p for p in ROOT.rglob("*") if p.is_dir()), key=rel)
    refs = references(files); records = []
    for path in dirs + files:
        key, reason = classify(path); is_dir = path.is_dir()
        size = sum(x.stat().st_size for x in path.rglob("*") if x.is_file()) if is_dir else path.stat().st_size
        records.append({"path": rel(path), "kind": "directory" if is_dir else "file", "category": CAT[key], "category_key": key, "size_bytes": size, "reason": reason, "references": refs.get(rel(path), [])})
    proposed_delete = [r for r in records if r["category_key"] == "cache" and r["kind"] == "file" and not r["references"]]
    # Existing archive contents are already archived. Do not propose a second move.
    proposed_archive = []
    totals = {label: {"files": 0, "directories": 0, "bytes": 0} for label in CAT.values()}
    for r in records:
        t = totals[r["category"]]; t["files"] += int(r["kind"] == "file"); t["directories"] += int(r["kind"] == "directory")
        if r["kind"] == "file": t["bytes"] += r["size_bytes"]
    report = {"schema_version": "astrakriti3d.cleanup-audit.v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(), "read_only": True, "project_root": str(ROOT), "inventory": {"file_count": len(files), "directory_count": len(dirs), "total_bytes": sum(p.stat().st_size for p in files)}, "category_totals": totals, "proposed_archive": proposed_archive, "proposed_deletion": proposed_delete, "deletion_policy": "No deletion performed. A deletion proposal requires human review; only unreferenced cache files are proposed.", "reference_method": "Literal relative-path and basename search across readable project text files; binary payloads are not parsed.", "ambiguous_historical_references": [r for r in records if r["references"] and r["category_key"] == "archive"], "records": records}
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Astrakriti3D cleanup audit", "", "Read-only audit. No file was deleted, moved, renamed, or modified by the audit.", "", f"Inventory: {len(files):,} files, {len(dirs):,} directories, {report['inventory']['total_bytes'] / 1e9:.3f} GB.", "", "## Category totals", "", "| Category | Files | Directories | Size (GB) |", "|---|---:|---:|---:|"]
    for label, t in totals.items(): lines.append(f"| {label} | {t['files']:,} | {t['directories']:,} | {t['bytes']/1e9:.3f} |")
    lines += ["", "## Proposed archive list", "", "No additional archive move is proposed; existing archive contents are retained.", ""] + ([f"- `{r['path']}` — {r['size_bytes']/1e9:.3f} GB" for r in proposed_archive] or ["- None"])
    lines += ["", "## Proposed deletion list", "", "Only unreferenced cache files are proposed; no deletion was performed.", ""] + ([f"- `{r['path']}` — {r['size_bytes']} bytes; references: none" for r in proposed_delete] or ["- None"])
    lines += ["", "## Reference and safety notes", "", "- Python imports, CLI entry points, tests, package metadata, documentation, configuration, and evidence references were scanned.", "- Evidence and experimental selector material is retained conservatively, even when old or unsuccessful.", "- `.env` is classified as unclear because it contains local credentials/configuration.", f"- {len(report['ambiguous_historical_references'])} archived records have literal basename/path matches in historical text; these are ambiguous evidence links, not deletion candidates.", "- Complete per-file and per-directory classifications are in `cleanup_audit.json`."]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT_JSON), "markdown": str(OUT_MD), "files": len(files), "directories": len(dirs), "proposed_delete": len(proposed_delete), "proposed_archive": len(proposed_archive)}, indent=2))

if __name__ == "__main__": main()

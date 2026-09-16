"""Versioned DJI-style SRT telemetry parsing and frame association."""
from __future__ import annotations
import csv, hashlib, json, math, re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

PARSER_VERSION = "1.0"
SCHEMA_VERSION = "phase3.telemetry.v1"

class TelemetryError(RuntimeError): pass
class MissingInputError(TelemetryError): pass
class UnsupportedSchemaError(TelemetryError): pass
class MalformedTelemetryError(TelemetryError): pass

@dataclass
class TelemetryRecord:
    record_id: str
    cue_start_seconds: float
    cue_end_seconds: float
    wall_clock_time: str | None
    latitude: float | None
    longitude: float | None
    altitude: float | None
    heading: float | None
    fields: dict
    raw_text: str
    valid: bool
    diagnostics: list[str]

def _cue_time(value: str) -> float:
    m = re.fullmatch(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
    if not m: raise ValueError(value)
    h, mi, s, ms = map(int, m.groups()); return h*3600 + mi*60 + s + ms/1000

def _num(text):
    try:
        v = float(text)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError): return None

def _coord(text, latitude):
    """Parse signed decimal coordinates and optional hemisphere suffix."""
    if text is None: return None
    m=re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*([NSEW])?\s*", str(text), re.I)
    if not m: return _num(text)
    value=float(m.group(1)); hemi=(m.group(2) or '').upper()
    if hemi in ('S','W'): value=-abs(value)
    return value

def _parse_block(block: str, ordinal: int) -> TelemetryRecord:
    lines = [x.strip() for x in block.splitlines() if x.strip()]
    diagnostics=[]
    if len(lines) < 3: raise MalformedTelemetryError(f"subtitle block {ordinal} is incomplete")
    cue = re.search(r"(\d\d:\d\d:\d\d[,.]\d{3})\s*-->\s*(\d\d:\d\d:\d\d[,.]\d{3})", lines[1])
    if not cue: raise MalformedTelemetryError(f"subtitle block {ordinal} has no supported cue timestamp")
    start, end = _cue_time(cue.group(1)), _cue_time(cue.group(2))
    raw = "\n".join(lines[2:])
    tags = {k.lower(): v.strip() for k,v in re.findall(r"\[\s*([A-Za-z_][\w]*)\s*:\s*([^\]]*)\]", raw)}
    if not ("latitude" in tags and "longitude" in tags):
        raise UnsupportedSchemaError(f"subtitle block {ordinal} lacks latitude/longitude fields")
    lat, lon = _coord(tags.get("latitude"), True), _coord(tags.get("longitude"), False)
    alt = _num(tags.get("altitude")); heading = _num(tags.get("heading"))
    if lat is None or lon is None: diagnostics.append("non-numeric coordinates")
    if lat is not None and not -90 <= lat <= 90: diagnostics.append("latitude outside [-90,90]")
    if lon is not None and not -180 <= lon <= 180: diagnostics.append("longitude outside [-180,180]")
    wall = None
    wm = re.search(r"(\d{4}-\d\d-\d\d\s+\d\d:\d\d:\d\d,\d{3},\d{3})", raw)
    if wm:
        wall = wm.group(1)
        # DJI uses milliseconds,microseconds after the seconds comma; retain
        # the vendor text without making an otherwise valid telemetry record
        # unusable when the optional wall-clock precision is nonstandard.
    valid = lat is not None and lon is not None and not any(x in diagnostics for x in ("non-numeric coordinates", "latitude outside [-90,90]", "longitude outside [-180,180]"))
    return TelemetryRecord(f"srt-{ordinal:06d}", start, end, wall, lat, lon, alt, heading, tags, raw, valid, diagnostics)

def parse_srt(path) -> tuple[list[TelemetryRecord], dict]:
    p=Path(path)
    if not p.is_file(): raise MissingInputError(f"SRT does not exist: {p}")
    raw=p.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n","\n").replace("\r","\n"))
    records=[]; errors=[]
    for i,b in enumerate(blocks,1):
        if not b.strip(): continue
        try: records.append(_parse_block(b,i))
        except (MalformedTelemetryError, UnsupportedSchemaError) as e: errors.append(str(e))
    if not records and errors: raise UnsupportedSchemaError("no supported telemetry records: " + errors[0])
    duplicates=[]; nonmono=[]
    for a,b in zip(records,records[1:]):
        if b.cue_start_seconds == a.cue_start_seconds: duplicates.append(b.record_id)
        if b.cue_start_seconds < a.cue_start_seconds: nonmono.append(b.record_id)
    gaps=[b.cue_start_seconds-a.cue_start_seconds for a,b in zip(records,records[1:]) if b.cue_start_seconds-a.cue_start_seconds > 1.0]
    semantics={"time_basis":"video-relative cue start; embedded wall-clock retained","coordinate_order":"latitude, longitude","altitude_interpretation":"unknown (SRT field labelled altitude; vertical datum/reference not supplied)","altitude_confidence":"unknown","heading":"not present in observed schema; preserved when supplied"}
    return records,{"parser_version":PARSER_VERSION,"schema_version":SCHEMA_VERSION,"source_sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"source_bytes":p.stat().st_size,"semantics":semantics,"raw_text":raw,"errors":errors,"duplicates":duplicates,"non_monotonic":nonmono,"gaps_seconds":gaps}

def _percentile(values, q):
    if not values: return None
    a=sorted(values); i=(len(a)-1)*q; lo=int(i); hi=min(lo+1,len(a)-1); return a[lo]+(a[hi]-a[lo])*(i-lo)

def associate(manifest, records, tolerance=0.5, time_offset=0.0):
    valid=sorted((r for r in records if r.valid), key=lambda r:r.cue_start_seconds)
    rows=[]; diffs=[]
    for frame in manifest:
        ft=float(frame.get("source_timestamp_seconds", frame.get("frame_timestamp_seconds", 0))) + time_offset
        best=min(valid,key=lambda r:abs(r.cue_start_seconds-ft),default=None)
        delta=(best.cue_start_seconds-ft) if best else None
        ok=best is not None and abs(delta)<=tolerance
        if ok: diffs.append(abs(delta))
        rows.append({"frame_filename":frame.get("output_filename") or frame.get("filename"),"frame_timestamp_seconds":ft-time_offset,"matched_telemetry_timestamp_seconds":best.cue_start_seconds if ok else None,"signed_time_difference_seconds":delta if ok else None,"telemetry_record_id":best.record_id if ok else None,"association_status":"matched" if ok else "unmatched","latitude":best.latitude if ok else None,"longitude":best.longitude if ok else None,"altitude":best.altitude if ok else None,"heading":best.heading if ok else None})
    return rows,diffs

def inspect_metadata(video, srt, manifest_path, output, tolerance=0.5, time_offset=0.0):
    for p,label in ((video,"video"),(manifest_path,"manifest")):
        if not Path(p).is_file(): raise MissingInputError(f"{label} does not exist: {p}")
    records, meta=parse_srt(srt)
    manifest=json.loads(Path(manifest_path).read_text(encoding="utf-8")); frames=manifest.get("frames",manifest if isinstance(manifest,list) else [])
    rows,diffs=associate(frames,records,tolerance,time_offset)
    raw=meta.pop("raw_text"); valid=sum(r.valid for r in records); matched=sum(x["association_status"]=="matched" for x in rows)
    report={"schema_version":SCHEMA_VERSION,"parser_version":PARSER_VERSION,"source_video":{"path":str(Path(video).resolve()),"sha256":hashlib.sha256(Path(video).read_bytes()).hexdigest()},"source_manifest":{"path":str(Path(manifest_path).resolve()),"sha256":hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()},"srt":{"path":str(Path(srt).resolve()),"sha256":meta["source_sha256"],"record_count":len(records),"valid_record_count":valid,"invalid_record_count":len(records)-valid,"timestamp_range_seconds":[records[0].cue_start_seconds,records[-1].cue_start_seconds] if records else None,**{k:v for k,v in meta.items() if k not in ("source_bytes",)},"altitude_units":"unknown","time_offset_seconds":time_offset},"association":{"configured_tolerance_seconds":tolerance,"frame_count":len(rows),"matched_count":matched,"unmatched_count":len(rows)-matched,"absolute_time_difference_seconds":{"minimum":min(diffs) if diffs else None,"median":_percentile(diffs,.5),"p95":_percentile(diffs,.95),"maximum":max(diffs) if diffs else None}},"warnings":meta["errors"]+["Altitude meaning is unknown; no geolocation submission performed."],"errors":[],"assumptions":["subtitle cue start is video-relative time","nearest valid record only; no interpolation across gaps"],"unknowns":["altitude vertical datum/reference","camera/gimbal orientation unless separately present"]}
    out=Path(output); out.mkdir(parents=True,exist_ok=True); (out/"telemetry_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8"); (out/"association_manifest.json").write_text(json.dumps({"schema_version":SCHEMA_VERSION,"rows":rows},indent=2),encoding="utf-8")
    with (out/"association_manifest.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ["frame_filename"]); w.writeheader(); w.writerows(rows)
    (out/"telemetry_ordered.json").write_text(json.dumps([asdict(r) for r in sorted(records,key=lambda x:x.cue_start_seconds)],indent=2),encoding="utf-8")
    return report

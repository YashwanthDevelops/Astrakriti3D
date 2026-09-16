"""Phase 4 geolocation preparation using one authoritative ODM geo.txt."""
from __future__ import annotations
import hashlib, json, shutil
from pathlib import Path

SCHEMA_VERSION="phase4.geolocation.v1"
class GeolocationError(RuntimeError): pass

def _sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def prepare_geolocation(video, frame_manifest, association_manifest, output, tolerance=0.5):
    fm=json.loads(Path(frame_manifest).read_text(encoding="utf-8")); frames=fm.get("frames",[])
    assoc=json.loads(Path(association_manifest).read_text(encoding="utf-8")); rows=assoc.get("rows",[])
    by_name={x.get("output_filename"):x for x in frames}; out=Path(output); imgout=out/"images"; imgout.mkdir(parents=True,exist_ok=True)
    if not rows: raise GeolocationError("association manifest contains no rows")
    prepared=[]; lines=["EPSG:4326"]
    for row in rows:
        name=row.get("frame_filename"); source=by_name.get(name)
        if not source or not source.get("output_path"): raise GeolocationError(f"frame missing from Phase 2 manifest: {name}")
        src=Path(source["output_path"])
        if not src.is_file(): raise GeolocationError(f"source image does not exist: {src}")
        if _sha(src)!=source.get("sha256"): raise GeolocationError(f"source image hash mismatch: {name}")
        if row.get("association_status")!="matched": raise GeolocationError(f"frame is not matched: {name}")
        delta=row.get("signed_time_difference_seconds")
        if delta is None or abs(float(delta))>tolerance: raise GeolocationError(f"association outside tolerance: {name}")
        lat,lon=row.get("latitude"),row.get("longitude")
        if lat is None or lon is None or not (-90<=float(lat)<=90) or not (-180<=float(lon)<=180): raise GeolocationError(f"invalid coordinates: {name}")
        dest=imgout/name; shutil.copy2(src,dest)
        # ODM geo.txt is filename longitude latitude [altitude], WGS84 degrees.
        lines.append(f"{name} {float(lon):.12f} {float(lat):.12f}")
        prepared.append({"image_filename":name,"frame_timestamp_seconds":row.get("frame_timestamp_seconds"),"telemetry_timestamp_seconds":row.get("matched_telemetry_timestamp_seconds"),"signed_time_difference_seconds":delta,"source":{"latitude":float(lat),"longitude":float(lon),"altitude":row.get("altitude"),"coordinate_order":"latitude, longitude","crs":"EPSG:4326","altitude_semantics":"unknown"},"prepared":{"geo_txt":"longitude latitude; altitude omitted","path":str(dest.resolve()),"sha256":_sha(dest)},"source_sha256":source["sha256"]})
    geo=out/"geo.txt"; geo.write_text("\n".join(lines)+"\n",encoding="utf-8")
    # Read back and compare serialized coordinates before reporting success.
    readback=[]
    serialized=geo.read_text(encoding="utf-8").splitlines()
    if not serialized or serialized[0] != "EPSG:4326": raise GeolocationError("geo.txt projection header is missing or incorrect")
    for line,row in zip(serialized[1:],prepared):
        parts=line.split();
        if len(parts)!=3 or parts[0]!=row["image_filename"]: raise GeolocationError("geo.txt read-back schema mismatch")
        readback.append({"image_filename":parts[0],"longitude":float(parts[1]),"latitude":float(parts[2])})
        if abs(readback[-1]["longitude"]-row["source"]["longitude"])>1e-11 or abs(readback[-1]["latitude"]-row["source"]["latitude"])>1e-11: raise GeolocationError("geo.txt coordinate read-back mismatch")
    report={"schema_version":SCHEMA_VERSION,"route":"odm_geo_txt","authoritative_source":"geo.txt only","source_video":{"path":str(Path(video).resolve()),"sha256":_sha(video)},"source_frame_manifest_sha256":_sha(frame_manifest),"source_association_manifest_sha256":_sha(association_manifest),"projection":{"header":"EPSG:4326","header_sha256":hashlib.sha256(b"EPSG:4326\n").hexdigest(),"crs":"EPSG:4326","datum":"WGS84","coordinate_order":"longitude latitude in geo.txt","altitude":"omitted; SRT altitude semantics unknown"},"tolerance_seconds":tolerance,"image_count":len(prepared),"geo_txt_sha256":_sha(geo),"prepared_images_sha256":hashlib.sha256(json.dumps([x["prepared"]["sha256"] for x in prepared]).encode()).hexdigest(),"readback_verified":True,"records":prepared,"warnings":["GPS coordinates support geographic alignment; they do not establish metric accuracy.","No EXIF GPS was written; no conflicting metadata source exists."],"webodm_submission":{"performed":False,"reason":"submission requires configured WebODM credentials and service"}}
    (out/"geolocation_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8"); (out/"prepared_manifest.json").write_text(json.dumps({"schema_version":SCHEMA_VERSION,"images":prepared},indent=2),encoding="utf-8")
    return report

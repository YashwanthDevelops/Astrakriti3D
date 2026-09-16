"""Coverage-aware deterministic selection for dense sequential candidates."""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import shutil
from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _distance_m(a, b):
    radius = 6371000.0
    lat = math.radians((a[1] + b[1]) / 2.0)
    dx = math.radians(b[0] - a[0]) * radius * math.cos(lat)
    dy = math.radians(b[1] - a[1]) * radius
    return math.hypot(dx, dy)


def _interpolated_positions(frames, telemetry_path):
    telemetry = json.loads(Path(telemetry_path).read_text(encoding="utf-8"))
    telemetry = [x for x in telemetry if x.get("valid", True)]
    times = [float(x["cue_start_seconds"]) for x in telemetry]
    positions = []
    for frame in frames:
        ts = float(frame["source_timestamp_seconds"])
        i = max(1, min(len(telemetry) - 1, bisect.bisect_left(times, ts)))
        left, right = telemetry[i - 1], telemetry[i]
        span = float(right["cue_start_seconds"]) - float(left["cue_start_seconds"])
        q = 0.0 if span <= 0 else (ts - float(left["cue_start_seconds"])) / span
        positions.append((
            float(left["longitude"]) + q * (float(right["longitude"]) - float(left["longitude"])),
            float(left["latitude"]) + q * (float(right["latitude"]) - float(left["latitude"])),
            float(left.get("altitude", 0.0)) + q * (float(right.get("altitude", 0.0)) - float(left.get("altitude", 0.0))),
        ))
    return positions


def coverage_aware_select(candidate_manifest, diagnostic_report, frames_dir, telemetry_path, output, *,
                          max_selected=280, min_selected=220, max_temporal_gap_seconds=2.0,
                          max_spatial_gap_m=7.0, time_window_seconds=2.0,
                          distance_window_m=10.0, min_new_feature_ratio=0.33,
                          max_feature_displacement=5.0, min_match_ratio=0.65,
                          turn_angle_degrees=20.0):
    candidate_manifest = Path(candidate_manifest)
    diagnostic_report = Path(diagnostic_report)
    frames_dir, output = Path(frames_dir), Path(output)
    frames = json.loads(candidate_manifest.read_text(encoding="utf-8"))["frames"]
    diagnostics = json.loads(diagnostic_report.read_text(encoding="utf-8"))["rows"]
    if len(frames) != len(diagnostics):
        raise ValueError("candidate and diagnostic row counts differ")
    positions = _interpolated_positions(frames, telemetry_path)
    cumulative = [0.0]
    for a, b in zip(positions, positions[1:]):
        cumulative.append(cumulative[-1] + _distance_m(a, b))
    route_length = cumulative[-1]
    turns = set()
    for i in range(2, len(frames) - 2):
        a, b, c = positions[i - 2], positions[i], positions[i + 2]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        n1, n2 = math.hypot(*v1), math.hypot(*v2)
        if n1 and n2:
            angle = math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))))
            if angle >= turn_angle_degrees:
                turns.add(i)
    time_bins = {}
    distance_bins = {}
    for i, frame in enumerate(frames):
        time_bins.setdefault(int(float(frame["source_timestamp_seconds"]) // time_window_seconds), []).append(i)
        distance_bins.setdefault(int(cumulative[i] // distance_window_m), []).append(i)
    selected = {0, len(frames) - 1} | turns
    reasons = {0: ["endpoint_protected"], len(frames) - 1: ["endpoint_protected"]}
    for i in turns:
        reasons.setdefault(i, []).append("turn_protected")
    def add_best(indices, reason):
        if not indices:
            return
        best = min(indices, key=lambda i: (len(reasons.get(i, [])), i))
        selected.add(best)
        reasons.setdefault(best, []).append(reason)
    for indices in time_bins.values():
        add_best(indices, "minimum_time_window_coverage")
    for indices in distance_bins.values():
        add_best(indices, "minimum_route_segment_coverage")
    last = 0
    rows = []
    for i, (frame, metric) in enumerate(zip(frames, diagnostics)):
        ts = float(frame["source_timestamp_seconds"])
        spatial_gap = cumulative[i] - cumulative[last] if selected else None
        temporal_gap = ts - float(frames[last]["source_timestamp_seconds"]) if selected else None
        feature_redundant = (i not in selected and float(metric.get("median_feature_displacement", 0.0)) <= max_feature_displacement
                             and float(metric.get("new_feature_ratio", 1.0)) <= min_new_feature_ratio
                             and float(metric.get("match_ratio", 0.0)) >= min_match_ratio)
        spatial_redundant = i not in selected and spatial_gap is not None and spatial_gap <= max_spatial_gap_m
        forced_continuity = i not in selected and (temporal_gap is not None and temporal_gap > max_temporal_gap_seconds)
        if forced_continuity:
            selected.add(i)
            reasons.setdefault(i, []).append("continuity_protected")
        elif i not in selected and not (feature_redundant and spatial_redundant):
            selected.add(i)
            reasons.setdefault(i, []).append("feature_or_spatial_change")
        rows.append({"frame_number": i + 1, "output_filename": frame["output_filename"],
                     "timestamp_seconds": ts, "longitude": positions[i][0], "latitude": positions[i][1],
                     "altitude": positions[i][2], "cumulative_route_m": cumulative[i],
                     "gps_gap_m": None if i == 0 else cumulative[i] - cumulative[i - 1],
                     "time_gap_from_previous_candidate_s": None if i == 0 else ts - float(frames[i - 1]["source_timestamp_seconds"]),
                     "feature_redundant": feature_redundant, "spatial_redundant": spatial_redundant,
                     "decision": "keep" if i in selected else "reject",
                     "reason": reasons.get(i, ["feature_and_spatial_redundancy_confirmed"])[0] if i not in selected else reasons.get(i, ["kept"])[0]})
        if i in selected:
            last = i
    # The streaming pass may retain more than the intended band because every non-redundant
    # candidate is kept. This is a diagnostic guard, never a blind truncation: reduce only
    # candidates that still satisfy both redundancy predicates, lowest-information first.
    if len(selected) > max_selected:
        ordered_selected = sorted(selected)
        removable = []
        for pos, i in enumerate(ordered_selected[1:-1], 1):
            if i in turns:
                continue
            previous_i, next_i = ordered_selected[pos - 1], ordered_selected[pos + 1]
            metric = diagnostics[i]
            feature_redundant = (float(metric.get("median_feature_displacement", 0.0)) <= max_feature_displacement
                                 and float(metric.get("new_feature_ratio", 1.0)) <= min_new_feature_ratio
                                 and float(metric.get("match_ratio", 0.0)) >= min_match_ratio)
            spatial_redundant = (cumulative[next_i] - cumulative[previous_i] <= 2.0 * max_spatial_gap_m
                                 and float(frames[next_i]["source_timestamp_seconds"]) - float(frames[previous_i]["source_timestamp_seconds"]) <= max_temporal_gap_seconds)
            if feature_redundant and spatial_redundant:
                removable.append(i)
        for i in removable:
            if len(selected) <= max_selected:
                break
            selected.remove(i)
            reasons.setdefault(i, []).append("redundancy_budget_rejection")
    # Re-establish the hard continuity invariant after any redundancy-budget removals.
    ordered_selected = sorted(selected)
    for previous_i, next_i in zip(ordered_selected, ordered_selected[1:]):
        gap = float(frames[next_i]["source_timestamp_seconds"]) - float(frames[previous_i]["source_timestamp_seconds"])
        if gap > max_temporal_gap_seconds:
            candidates = [i for i in range(previous_i + 1, next_i) if i not in selected]
            while gap > max_temporal_gap_seconds and candidates:
                chosen = min(candidates, key=lambda i: abs(float(frames[i]["source_timestamp_seconds"]) - (float(frames[previous_i]["source_timestamp_seconds"]) + max_temporal_gap_seconds)))
                selected.add(chosen)
                reasons.setdefault(chosen, []).append("continuity_protected")
                candidates.remove(chosen)
                ordered_selected = sorted(selected)
                next_i = min(x for x in ordered_selected if x > previous_i)
                gap = float(frames[next_i]["source_timestamp_seconds"]) - float(frames[previous_i]["source_timestamp_seconds"])
    if len(selected) < min_selected:
        raise ValueError(f"coverage-aware selector retained only {len(selected)} frames")
    selected_indices = sorted(selected)
    out_frames = output / "frames"
    out_frames.mkdir(parents=True, exist_ok=True)
    selected_records = []
    for i in selected_indices:
        frame = frames[i]
        src = Path(frame.get("output_path") or frames_dir / frame["output_filename"])
        if frame.get("sha256") and _sha(src) != frame["sha256"]:
            raise ValueError(f"source hash mismatch: {src.name}")
        dst = out_frames / src.name
        shutil.copy2(src, dst)
        selected_records.append({"output_filename": src.name, "source_timestamp_seconds": frame["source_timestamp_seconds"],
                                 "source_frame_index": frame.get("source_frame_index"), "source_sha256": frame.get("sha256") or _sha(src),
                                 "sha256": _sha(dst), "longitude": positions[i][0], "latitude": positions[i][1], "altitude": positions[i][2]})
    geo = output / "geo.txt"
    geo.write_text("EPSG:4326\n" + "\n".join(f"{x['output_filename']} {x['longitude']:.12f} {x['latitude']:.12f}" for x in selected_records) + "\n", encoding="utf-8")
    selected_set = {x["output_filename"] for x in selected_records}
    ordered = all(selected_records[i]["source_timestamp_seconds"] <= selected_records[i + 1]["source_timestamp_seconds"] for i in range(len(selected_records) - 1))
    report = {"schema_version": "coverage-aware-selection.v1", "candidate_count": len(frames), "selected_count": len(selected_records),
              "rejected_count": len(frames) - len(selected_records), "route_length_m": route_length,
              "configuration": {"max_temporal_gap_seconds": max_temporal_gap_seconds, "max_spatial_gap_m": max_spatial_gap_m,
                                "time_window_seconds": time_window_seconds, "distance_window_m": distance_window_m,
                                "min_new_feature_ratio": min_new_feature_ratio, "max_feature_displacement": max_feature_displacement,
                                "min_match_ratio": min_match_ratio, "turn_angle_degrees": turn_angle_degrees},
              "selected": selected_records, "rows": rows, "geo_validation": {"record_count": len(selected_records), "names_match": selected_set == {x["output_filename"] for x in selected_records}, "chronological": ordered, "geo_sha256": _sha(geo)},
              "deterministic": True}
    (output / "selection_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def coverage_aware_select_streaming(candidate_manifest, diagnostic_report, frames_dir, telemetry_path, output, *,
                                    max_temporal_gap_seconds=2.0, max_spatial_gap_m=7.0,
                                    min_new_feature_ratio=0.33, max_feature_displacement=5.0,
                                    min_match_ratio=0.65, turn_angle_degrees=45.0):
    """Greedy coverage selector with hard temporal/spatial continuity invariants."""
    candidate_manifest, diagnostic_report = Path(candidate_manifest), Path(diagnostic_report)
    frames_dir, output = Path(frames_dir), Path(output)
    frames = json.loads(candidate_manifest.read_text(encoding="utf-8"))["frames"]
    diagnostics = json.loads(diagnostic_report.read_text(encoding="utf-8"))["rows"]
    positions = _interpolated_positions(frames, telemetry_path)
    cumulative = [0.0]
    for a, b in zip(positions, positions[1:]): cumulative.append(cumulative[-1] + _distance_m(a, b))
    turns = set()
    for i in range(2, len(frames) - 2):
        a, b, c = positions[i - 2], positions[i], positions[i + 2]
        v1, v2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
        n1, n2 = math.hypot(*v1), math.hypot(*v2)
        if n1 and n2 and math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2))))) >= turn_angle_degrees: turns.add(i)
    selected = [0]
    rows = []
    for i, (frame, metric) in enumerate(zip(frames, diagnostics)):
        last = selected[-1]
        time_gap = float(frame["source_timestamp_seconds"]) - float(frames[last]["source_timestamp_seconds"])
        spatial_gap = _distance_m(positions[last], positions[i])
        feature_redundant = (i not in (0, len(frames) - 1) and i not in turns and
                             float(metric.get("median_feature_displacement", 0.0)) <= max_feature_displacement and
                             float(metric.get("new_feature_ratio", 1.0)) <= min_new_feature_ratio and
                             float(metric.get("match_ratio", 0.0)) >= min_match_ratio)
        spatial_redundant = i not in (0, len(frames) - 1) and spatial_gap <= max_spatial_gap_m
        continuity = i == 0 or time_gap > max_temporal_gap_seconds or spatial_gap > max_spatial_gap_m
        if i + 1 < len(frames):
            next_time_gap = float(frames[i + 1]["source_timestamp_seconds"]) - float(frame["source_timestamp_seconds"])
            next_spatial_gap = _distance_m(positions[i], positions[i + 1])
            lookahead = (next_time_gap > max_temporal_gap_seconds or next_spatial_gap > max_spatial_gap_m or
                         _distance_m(positions[last], positions[i + 1]) > max_spatial_gap_m)
        else:
            lookahead = False
        keep = i == 0 or i == len(frames) - 1 or i in turns or continuity or lookahead or not (feature_redundant and spatial_redundant)
        reason = ("endpoint_protected" if i in (0, len(frames) - 1) else "turn_protected" if i in turns else
                  "continuity_protected" if continuity else "feature_and_spatial_redundancy_confirmed" if not keep else "feature_or_spatial_change")
        if keep and (not selected or selected[-1] != i): selected.append(i)
        rows.append({"frame_number": i + 1, "output_filename": frame["output_filename"], "timestamp_seconds": float(frame["source_timestamp_seconds"]),
                     "longitude": positions[i][0], "latitude": positions[i][1], "cumulative_route_m": cumulative[i],
                     "gps_gap_m_from_last_selected": spatial_gap, "time_gap_s_from_last_selected": time_gap,
                     "feature_redundant": feature_redundant, "spatial_redundant": spatial_redundant,
                     "decision": "keep" if keep else "reject", "reason": reason})
    # Endpoint protection must not create a final temporal hole.
    for previous_i, next_i in list(zip(selected, selected[1:])):
        gap = float(frames[next_i]["source_timestamp_seconds"]) - float(frames[previous_i]["source_timestamp_seconds"])
        if gap > max_temporal_gap_seconds:
            for candidate_i in range(previous_i + 1, next_i):
                if candidate_i not in selected:
                    candidate_gap = float(frames[candidate_i]["source_timestamp_seconds"]) - float(frames[previous_i]["source_timestamp_seconds"])
                    if candidate_gap >= max_temporal_gap_seconds * 0.75:
                        selected.append(candidate_i)
                        rows[candidate_i]["decision"] = "keep"
                        rows[candidate_i]["reason"] = "continuity_protected"
                        break
            selected.sort()
    output_frames = output / "frames"; output_frames.mkdir(parents=True, exist_ok=True)
    selected_records = []
    for i in selected:
        frame = frames[i]; src = Path(frame.get("output_path") or frames_dir / frame["output_filename"])
        if frame.get("sha256") and _sha(src) != frame["sha256"]: raise ValueError(f"source hash mismatch: {src.name}")
        dst = output_frames / src.name; shutil.copy2(src, dst)
        selected_records.append({"output_filename": src.name, "source_timestamp_seconds": frame["source_timestamp_seconds"], "source_frame_index": frame.get("source_frame_index"), "source_sha256": frame.get("sha256") or _sha(src), "sha256": _sha(dst), "longitude": positions[i][0], "latitude": positions[i][1], "altitude": positions[i][2], "cumulative_route_m": cumulative[i]})
    geo = output / "geo.txt"
    geo.write_text("EPSG:4326\n" + "\n".join(f"{x['output_filename']} {x['longitude']:.12f} {x['latitude']:.12f}" for x in selected_records) + "\n", encoding="utf-8")
    report = {"schema_version": "coverage-aware-selection.v2", "candidate_count": len(frames), "selected_count": len(selected_records), "rejected_count": len(frames) - len(selected_records), "route_length_m": cumulative[-1], "configuration": {"max_temporal_gap_seconds": max_temporal_gap_seconds, "max_spatial_gap_m": max_spatial_gap_m, "min_new_feature_ratio": min_new_feature_ratio, "max_feature_displacement": max_feature_displacement, "min_match_ratio": min_match_ratio, "turn_angle_degrees": turn_angle_degrees, "coverage_rule": "reject only when feature and spatial redundancy are both confirmed"}, "selected": selected_records, "rows": rows, "geo_validation": {"record_count": len(selected_records), "names_match": True, "chronological": True, "geo_sha256": _sha(geo)}, "deterministic": True}
    (output / "selection_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report

"""Create a reproducible, non-destructive Phase 4 video/SRT fixture."""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


_CUE = re.compile(
    r"(?P<start>\d\d:\d\d:\d\d,\d{3})\s*-->\s*"
    r"(?P<end>\d\d:\d\d:\d\d,\d{3})"
)


def seconds(value: str) -> float:
    h, m, rest = value.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def stamp(value: float) -> str:
    millis = int(round(value * 1000))
    h, millis = divmod(millis, 3_600_000)
    m, millis = divmod(millis, 60_000)
    s, millis = divmod(millis, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"


def trim_srt(source: Path, destination: Path, start: float, end: float) -> int:
    text = source.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
    selected = []
    for block in blocks:
        match = _CUE.search(block)
        if not match:
            continue
        cue_start, cue_end = seconds(match.group("start")), seconds(match.group("end"))
        if cue_start >= end or cue_end <= start:
            continue
        shifted_start = max(cue_start, start) - start
        shifted_end = min(cue_end, end) - start
        replacement = f"{stamp(shifted_start)} --> {stamp(shifted_end)}"
        selected.append(_CUE.sub(replacement, block, count=1))
    if not selected:
        raise ValueError("no SRT cues overlap the requested video interval")
    destination.write_text("\n\n".join(selected) + "\n", encoding="utf-8")
    return len(selected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("srt", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--duration", type=float, default=60.0)
    args = parser.parse_args()
    if not args.video.is_file() or not args.srt.is_file():
        raise FileNotFoundError("source video and SRT must both exist")
    if args.start < 0 or args.duration <= 0:
        raise ValueError("start must be non-negative and duration must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    output_video = args.output / args.video.name
    output_srt = args.output / args.srt.name
    if output_video.exists() or output_srt.exists():
        raise FileExistsError("refusing to overwrite an existing Phase 4 fixture")
    end = args.start + args.duration
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(args.start),
         "-i", str(args.video), "-t", str(args.duration), "-map", "0:v:0",
         "-c", "copy", "-avoid_negative_ts", "make_zero", "-y", str(output_video)],
        check=True,
    )
    count = trim_srt(args.srt, output_srt, args.start, end)
    print({"video": str(output_video), "srt": str(output_srt), "start": args.start,
           "end": end, "duration": args.duration, "cue_count": count})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

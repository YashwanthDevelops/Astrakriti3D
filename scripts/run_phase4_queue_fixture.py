"""Run the Phase 4 preparation queue against a real video/SRT fixture."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from astrakriti3d.orchestrator import PreparationQueue


def main(video, srt, output, state):
    queue = PreparationQueue(state)
    queue.submit("real-phase4-1min", video, output, mode="georeferenced", srt=srt,
                 interval_seconds=2.0, extraction_mode="seek", tolerance=0.5)
    started = time.monotonic()
    while time.monotonic() - started < 300:
        status = queue.status("real-phase4-1min")
        if status["status"] in {"completed", "failed", "cancelled"}:
            print(json.dumps(status, indent=2))
            return 0 if status["status"] == "completed" else 1
        time.sleep(1)
    print(json.dumps(queue.status("real-phase4-1min"), indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main(*(Path(x) for x in sys.argv[1:5])))

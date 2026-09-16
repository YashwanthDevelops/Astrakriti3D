"""Offline resource and OpenCV threading checks used before experiments."""
from __future__ import annotations
import os, time
from dataclasses import asdict, dataclass

@dataclass(frozen=True)
class ResourceSnapshot:
    available_memory_bytes: int
    process_memory_bytes: int
    cpu_percent: float
    cpu_count: int
    configured_thread_count: int

def configure_threads(thread_count: int | None = None) -> int:
    """Set a bounded OpenCV thread count; never starts an engine process."""
    count = int(thread_count if thread_count is not None else os.environ.get("ASTRAKRITI_THREADS", "1"))
    if count < 1: raise ValueError("thread_count must be at least 1")
    os.environ["OMP_NUM_THREADS"] = str(count)
    os.environ["MKL_NUM_THREADS"] = str(count)
    try:
        import cv2
        cv2.setNumThreads(count)
    except Exception:
        pass
    return count

def snapshot(thread_count: int | None = None) -> dict:
    import psutil
    proc = psutil.Process()
    count = configure_threads(thread_count)
    psutil.cpu_percent(interval=None)
    time.sleep(0.01)
    value = ResourceSnapshot(int(psutil.virtual_memory().available), int(proc.memory_info().rss), float(psutil.cpu_percent(interval=None)), os.cpu_count() or 1, count)
    return asdict(value)

def require_memory(minimum_bytes: int, thread_count: int | None = None) -> dict:
    result = snapshot(thread_count)
    result["minimum_required_memory_bytes"] = int(minimum_bytes)
    result["memory_sufficient"] = result["available_memory_bytes"] >= int(minimum_bytes)
    if not result["memory_sufficient"]:
        raise MemoryError(f"insufficient available memory: {result['available_memory_bytes']} < {minimum_bytes} bytes")
    return result

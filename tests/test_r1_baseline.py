import json
from pathlib import Path

from scripts.validate_r1_baseline import validate


def test_frozen_r1_baseline_is_valid():
    root = Path(__file__).resolve().parents[1]
    result = validate(root, root / "config" / "r1_baseline.json")
    assert result["valid"], result["issues"]


def test_baseline_declares_production_status_and_experimental_alternatives():
    root = Path(__file__).resolve().parents[1]
    spec = json.loads((root / "config" / "r1_baseline.json").read_text(encoding="utf-8"))
    assert spec["status"] == "official-production-baseline"
    assert spec["extraction"]["expected_frame_count"] == 194
    assert spec["webodm"]["options_override"] == []

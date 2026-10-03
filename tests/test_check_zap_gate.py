"""Tests for ZAP gate helper (used in CI)."""
import json
import subprocess
import sys
from pathlib import Path


def test_zap_gate_passes_with_no_high(tmp_path):
    report = {
        "site": [
            {
                "alerts": [
                    {"riskdesc": "Low (Medium)"},
                    {"riskdesc": "Informational (Low)"},
                ]
            }
        ]
    }
    path = tmp_path / "zap.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/check_zap_gate.py", str(path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_zap_gate_fails_on_high(tmp_path):
    report = {"site": [{"alerts": [{"riskdesc": "High (High)"}]}]}
    path = tmp_path / "zap.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/check_zap_gate.py", str(path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1

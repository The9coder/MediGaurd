"""
tests/test_quality_gate.py – Tests for scripts/quality_gate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.quality_gate import load_config, run_gate, DEFAULT_THRESHOLDS


def make_summary(counts: dict) -> dict:
    """Build a minimal summary dict for testing."""
    return {
        "generated_at": "2024-01-01T00:00:00Z",
        "total_findings": sum(counts.values()),
        "counts": counts,
        "findings": [],
    }


class TestLoadConfig:
    def test_defaults_on_missing_file(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yml")
        assert config["CRITICAL"] == DEFAULT_THRESHOLDS["CRITICAL"]

    def test_loads_yaml(self, tmp_path):
        yml = tmp_path / "gate.yml"
        yml.write_text("thresholds:\n  CRITICAL: 2\n  HIGH: 10\n", encoding="utf-8")
        config = load_config(yml)
        assert config["CRITICAL"] == 2
        assert config["HIGH"] == 10


class TestRunGate:
    def test_pass_all_within_threshold(self):
        summary = make_summary({"CRITICAL": 0, "HIGH": 3, "MEDIUM": 10, "LOW": 50})
        assert run_gate(summary, DEFAULT_THRESHOLDS) is True

    def test_fail_on_critical(self):
        summary = make_summary({"CRITICAL": 1, "HIGH": 0, "MEDIUM": 0, "LOW": 0})
        assert run_gate(summary, DEFAULT_THRESHOLDS) is False

    def test_fail_on_high_exceeded(self):
        summary = make_summary({"CRITICAL": 0, "HIGH": 10, "MEDIUM": 0, "LOW": 0})
        assert run_gate(summary, DEFAULT_THRESHOLDS) is False

    def test_pass_high_at_threshold(self):
        summary = make_summary({"CRITICAL": 0, "HIGH": 5, "MEDIUM": 0, "LOW": 0})
        assert run_gate(summary, DEFAULT_THRESHOLDS) is True

    def test_empty_findings_pass(self):
        summary = make_summary({"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0})
        assert run_gate(summary, DEFAULT_THRESHOLDS) is True

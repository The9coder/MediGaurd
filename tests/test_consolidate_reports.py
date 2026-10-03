"""
tests/test_consolidate_reports.py – Tests for scripts/consolidate_reports.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SAMPLE_DIR = ROOT / "tests" / "sample_reports"
sys.path.insert(0, str(ROOT))

from scripts.consolidate_reports import (
    parse_bandit,
    parse_pip_audit,
    parse_trivy,
    parse_zap,
    consolidate,
    render_html,
)


# ── Bandit parser ─────────────────────────────────────────────────────────────

class TestParseBandit:
    def test_returns_list(self):
        findings = parse_bandit(SAMPLE_DIR / "bandit.json")
        assert isinstance(findings, list)

    def test_count(self):
        findings = parse_bandit(SAMPLE_DIR / "bandit.json")
        assert len(findings) == 3

    def test_tool_field(self):
        findings = parse_bandit(SAMPLE_DIR / "bandit.json")
        assert all(f["tool"] == "bandit" for f in findings)

    def test_severity_present(self):
        findings = parse_bandit(SAMPLE_DIR / "bandit.json")
        for f in findings:
            assert f["severity"] in ("HIGH", "MEDIUM", "LOW", "CRITICAL", "INFO", "UNKNOWN")

    def test_missing_file_returns_empty(self, tmp_path):
        findings = parse_bandit(tmp_path / "nonexistent.json")
        assert findings == []


# ── pip-audit parser ──────────────────────────────────────────────────────────

class TestParsePipAudit:
    def test_returns_list(self):
        findings = parse_pip_audit(SAMPLE_DIR / "pip-audit.json")
        assert isinstance(findings, list)

    def test_count(self):
        # 3 packages × 1 vuln each = 3 findings
        findings = parse_pip_audit(SAMPLE_DIR / "pip-audit.json")
        assert len(findings) == 3

    def test_tool_field(self):
        findings = parse_pip_audit(SAMPLE_DIR / "pip-audit.json")
        assert all(f["tool"] == "pip-audit" for f in findings)

    def test_location_contains_version(self):
        findings = parse_pip_audit(SAMPLE_DIR / "pip-audit.json")
        for f in findings:
            assert "==" in f["location"]


# ── Trivy parser ──────────────────────────────────────────────────────────────

class TestParseTrivy:
    def test_returns_list(self):
        findings = parse_trivy(SAMPLE_DIR / "trivy.json")
        assert isinstance(findings, list)

    def test_count(self):
        findings = parse_trivy(SAMPLE_DIR / "trivy.json")
        assert len(findings) == 2

    def test_tool_field(self):
        findings = parse_trivy(SAMPLE_DIR / "trivy.json")
        assert all(f["tool"] == "trivy" for f in findings)


# ── ZAP parser ────────────────────────────────────────────────────────────────

class TestParseZap:
    def test_returns_list(self):
        findings = parse_zap(SAMPLE_DIR / "zap.json")
        assert isinstance(findings, list)

    def test_count(self):
        # 2 alerts
        findings = parse_zap(SAMPLE_DIR / "zap.json")
        assert len(findings) == 2

    def test_tool_field(self):
        findings = parse_zap(SAMPLE_DIR / "zap.json")
        assert all(f["tool"] == "zap" for f in findings)


# ── Consolidation ─────────────────────────────────────────────────────────────

class TestConsolidate:
    def _all_findings(self):
        return (
            parse_bandit(SAMPLE_DIR / "bandit.json")
            + parse_pip_audit(SAMPLE_DIR / "pip-audit.json")
            + parse_trivy(SAMPLE_DIR / "trivy.json")
            + parse_zap(SAMPLE_DIR / "zap.json")
        )

    def test_total_findings(self):
        summary = consolidate(self._all_findings())
        assert summary["total_findings"] == 3 + 3 + 2 + 2  # 10

    def test_counts_are_dict(self):
        summary = consolidate(self._all_findings())
        assert isinstance(summary["counts"], dict)

    def test_has_generated_at(self):
        summary = consolidate(self._all_findings())
        assert "generated_at" in summary

    def test_findings_sorted_by_severity(self):
        findings = self._all_findings()
        summary = consolidate(findings)
        sev_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]
        sev_rank = {s: i for i, s in enumerate(sev_order)}
        ranks = [sev_rank.get(f["severity"], 99) for f in summary["findings"]]
        assert ranks == sorted(ranks), "Findings not sorted by severity"


# ── HTML rendering ────────────────────────────────────────────────────────────

class TestRenderHtml:
    def test_returns_string(self):
        summary = consolidate([])
        html = render_html(summary)
        assert isinstance(html, str)

    def test_contains_title(self):
        summary = consolidate([])
        html = render_html(summary)
        assert "MediGuard" in html

    def test_contains_findings(self):
        findings = parse_bandit(SAMPLE_DIR / "bandit.json")
        summary = consolidate(findings)
        html = render_html(summary)
        assert "bandit" in html

    def test_output_is_html(self):
        summary = consolidate([])
        html = render_html(summary)
        assert "<!DOCTYPE html>" in html

    def test_roundtrip_json(self, tmp_path):
        """Consolidate → write JSON → reload → counts match."""
        findings = parse_bandit(SAMPLE_DIR / "bandit.json")
        summary = consolidate(findings)
        json_path = tmp_path / "summary.json"
        json_path.write_text(json.dumps(summary), encoding="utf-8")
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        assert loaded["total_findings"] == summary["total_findings"]
        assert loaded["counts"] == summary["counts"]

"""Tests for release security report aggregation."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_release_security_report import build_report


def test_build_report_fail_when_gate_failed(tmp_path):
    bandit_path = tmp_path / "bandit.json"
    bandit_path.write_text(
        json.dumps(
            {
                "metrics": {"_totals": {"SEVERITY.HIGH": 2, "SEVERITY.MEDIUM": 0, "SEVERITY.LOW": 0}},
                "results": [
                    {
                        "issue_severity": "HIGH",
                        "issue_confidence": "HIGH",
                        "filename": "app/routes/patients.py",
                        "line_number": 31,
                        "issue_text": "SQL injection",
                        "test_id": "B608",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload, md = build_report(
        tmp_path,
        {
            "lint": "success",
            "sast": "failure",
            "sca": "failure",
            "secrets": "failure",
            "tests": "success",
            "container": "success",
            "dast": "failure",
        },
    )
    assert payload["release_decision"] == "FAIL"
    assert "SQL injection" in md
    assert payload["severity_counts"]["sast_high"] == 2

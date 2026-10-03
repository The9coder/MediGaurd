"""Extra tests to cover the remaining error-handling and report-generation branches."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mysql.connector import IntegrityError, Error as MySQLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.consolidate_reports import main as consolidate_main


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "dob": "1980-01-02", "gender": "F", "diagnosis": "ok"},
        {"name": "Jane", "dob": "not-a-date", "gender": "F", "diagnosis": "ok"},
        {"name": "Jane", "dob": "1980-01-02", "gender": "X", "diagnosis": "ok"},
        {"name": "Jane", "dob": "1980-01-02", "gender": "F", "diagnosis": "x" * 256},
    ],
)
def test_patient_creation_validation_errors(client, auth_headers, payload):
    response = client.post("/patients", headers=auth_headers, json=payload)
    assert response.status_code == 400


def test_not_found_and_method_not_allowed(client):
    assert client.get("/definitely-missing").status_code == 404
    assert client.post("/health").status_code == 405


@patch("app.routes.auth.get_db")
def test_register_handles_integrity_error(mock_get_db, client):
    cursor = MagicMock()
    cursor.execute.side_effect = IntegrityError("duplicate username")
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.post(
        "/register",
        json={"username": "taken_user", "password": "strong-password"},
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == "Username is already taken"


@patch("app.routes.auth.get_db")
def test_register_handles_db_service_error(mock_get_db, client):
    cursor = MagicMock()
    cursor.execute.side_effect = MySQLError("db down")
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.post(
        "/register",
        json={"username": "new_user", "password": "strong-password"},
    )

    assert response.status_code == 503
    assert "temporarily unavailable" in response.get_json()["error"]


@patch("app.routes.auth.get_db")
def test_login_handles_db_lookup_error(mock_get_db, client):
    cursor = MagicMock()
    cursor.execute.side_effect = MySQLError("db down")
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.post(
        "/login",
        json={"username": "someuser", "password": "passphrase123"},
    )

    assert response.status_code == 503
    assert "temporarily unavailable" in response.get_json()["error"]


def test_parse_log_accepts_json_line_entries(tmp_path):
    log_path = tmp_path / "json_access.log"
    log_path.write_text(
        json.dumps(
            {
                "ts": "2024-01-01T00:00:00Z",
                "ip": "10.0.0.7",
                "method": "POST",
                "path": "/login",
                "status": 401,
                "user": "anonymous",
                "duration_ms": 12.5,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    from scripts.log_analyzer import parse_log

    events = parse_log(log_path)
    assert events == [{"ts": "2024-01-01T00:00:00Z", "ip": "10.0.0.7", "user": "anonymous"}]


def test_consolidate_reports_main_generates_outputs(tmp_path):
    bandit = tmp_path / "bandit.json"
    pip_audit = tmp_path / "pip-audit.json"
    trivy = tmp_path / "trivy.json"
    zap = tmp_path / "zap.json"

    bandit.write_text(
        json.dumps({"results": [{"issue_severity": "HIGH", "test_id": "B101", "issue_text": "Test", "filename": "app.py", "line_number": 7, "more_info": "info"}]}),
        encoding="utf-8",
    )
    pip_audit.write_text(
        json.dumps([
            {"name": "urllib3", "version": "1.26.0", "vulns": [{"id": "CVE-1", "description": "bad", "fix_versions": ["1.26.1"]}]}
        ]),
        encoding="utf-8",
    )
    trivy.write_text(
        json.dumps({"Results": [{"Vulnerabilities": [{"Severity": "MEDIUM", "VulnerabilityID": "CVE-2", "Title": "bad pkg", "PkgName": "requests", "InstalledVersion": "2.0.0", "FixedVersion": "2.0.1", "Description": "desc"}]}]}),
        encoding="utf-8",
    )
    zap.write_text(
        json.dumps({"site": [{"alerts": [{"riskdesc": "High Risk", "alert": "XSS", "desc": "desc", "instances": [{"uri": "https://example.com"}]}]}]}),
        encoding="utf-8",
    )

    out_dir = tmp_path / "reports"
    consolidate_main(
        SimpleNamespace(
            bandit=str(bandit),
            pip_audit=str(pip_audit),
            trivy=str(trivy),
            zap=str(zap),
            out_dir=str(out_dir),
        )
    )

    summary_path = out_dir / "summary.json"
    html_path = out_dir / "summary.html"
    assert summary_path.exists()
    assert html_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["total_findings"] >= 4
    assert "MediGuard" in html_path.read_text(encoding="utf-8")

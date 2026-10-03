"""
Tests for log_analyzer.py
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pathlib import Path
from scripts.log_analyzer import parse_log, analyze, write_report

SAMPLE_LOG = """\
2024-01-15 12:00:01,000 | WARNING | LOGIN_FAILED | ip=10.0.0.1 username=admin
2024-01-15 12:00:02,000 | WARNING | LOGIN_FAILED | ip=10.0.0.1 username=admin
2024-01-15 12:00:03,000 | WARNING | LOGIN_FAILED | ip=10.0.0.1 username=root
2024-01-15 12:00:04,000 | INFO    | LOGIN_SUCCESS | ip=10.0.0.2 username=clinician
2024-01-15 12:00:05,000 | WARNING | LOGIN_FAILED | ip=10.0.0.3 username=test
2024-01-15 12:00:06,000 | WARNING | LOGIN_FAILED | ip=10.0.0.1 username=admin
2024-01-15 12:00:07,000 | WARNING | LOGIN_FAILED | ip=10.0.0.1 username=admin
2024-01-15 12:00:08,000 | WARNING | LOGIN_FAILED | ip=10.0.0.1 username=sa
"""


def test_parse_log_counts(tmp_path):
    log_file = tmp_path / "access.log"
    log_file.write_text(SAMPLE_LOG)
    events = parse_log(log_file)
    # 6 LOGIN_FAILED lines for 10.0.0.1, 1 for 10.0.0.3
    assert len(events) == 7


def test_parse_log_missing_file(tmp_path):
    events = parse_log(tmp_path / "nonexistent.log")
    assert events == []


def test_analyze_flags_above_threshold():
    events = [
        {"ip": "10.0.0.1", "user": "admin", "ts": "2024-01-15 12:00:01"},
        {"ip": "10.0.0.1", "user": "admin", "ts": "2024-01-15 12:00:02"},
        {"ip": "10.0.0.1", "user": "root",  "ts": "2024-01-15 12:00:03"},
        {"ip": "10.0.0.1", "user": "admin", "ts": "2024-01-15 12:00:04"},
        {"ip": "10.0.0.1", "user": "admin", "ts": "2024-01-15 12:00:05"},
        {"ip": "10.0.0.1", "user": "sa",    "ts": "2024-01-15 12:00:06"},
        {"ip": "10.0.0.3", "user": "test",  "ts": "2024-01-15 12:00:07"},
    ]
    flagged = analyze(events, threshold=5)
    assert "10.0.0.1" in flagged
    assert flagged["10.0.0.1"]["attempts"] == 6
    assert "10.0.0.3" not in flagged


def test_analyze_no_flags_below_threshold():
    events = [{"ip": "10.0.0.1", "user": "admin", "ts": "t"}] * 3
    flagged = analyze(events, threshold=5)
    assert flagged == {}


def test_write_report(tmp_path):
    flagged = {
        "10.0.0.1": {"attempts": 6, "usernames_tried": ["admin", "root", "sa"]}
    }
    out = tmp_path / "report.txt"
    write_report(flagged, total_events=7, threshold=5, out_path=out)
    content = out.read_text()
    assert "10.0.0.1" in content
    assert "Suspicious IPs flagged" in content

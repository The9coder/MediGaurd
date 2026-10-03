"""
scripts/quality_gate.py – DevSecOps Quality Gate
=================================================
Reads reports/summary.json and gate_config.yml.
Exits with code 1 (FAIL) if any severity count exceeds its threshold.
Exits with code 0 (PASS) otherwise.

Usage:
    python scripts/quality_gate.py \\
        --summary  reports/summary.json \\
        --config   gate_config.yml

In a CI pipeline, a non-zero exit blocks the deployment stage.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml  # PyYAML

log = logging.getLogger(__name__)
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s",
                    level=logging.INFO, stream=sys.stdout)

# Default thresholds if gate_config.yml is missing or incomplete
DEFAULT_THRESHOLDS: dict[str, int] = {
    "CRITICAL": 0,   # Any CRITICAL → fail
    "HIGH":     5,   # Up to 5 HIGH allowed (e.g. known false positives)
    "MEDIUM":   20,
    "LOW":      100,
}


def load_config(config_path: Path) -> dict[str, int]:
    """Load thresholds from gate_config.yml, falling back to defaults."""
    if not config_path.exists():
        log.warning("gate_config.yml not found at %s; using defaults.", config_path)
        return DEFAULT_THRESHOLDS
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    thresholds = raw.get("thresholds", {})
    merged = {**DEFAULT_THRESHOLDS, **{k.upper(): int(v) for k, v in thresholds.items()}}
    log.info("Loaded gate thresholds: %s", merged)
    return merged


def load_summary(summary_path: Path) -> dict:
    """Load the consolidated summary JSON."""
    if not summary_path.exists():
        log.error("summary.json not found at %s. Run consolidate_reports.py first.", summary_path)
        sys.exit(2)
    with open(summary_path, encoding="utf-8") as f:
        return json.load(f)


def run_gate(summary: dict, thresholds: dict[str, int]) -> bool:
    """
    Returns True (PASS) if all counts are within thresholds.
    Returns False (FAIL) if any threshold is exceeded.
    """
    counts = summary.get("counts", {})
    passed = True

    log.info("=" * 55)
    log.info("MediGuard Quality Gate")
    log.info("=" * 55)
    log.info("%-12s %8s %8s %8s", "Severity", "Count", "Max", "Status")
    log.info("-" * 55)

    for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = counts.get(severity, 0)
        threshold = thresholds.get(severity, DEFAULT_THRESHOLDS.get(severity, 999))
        ok = count <= threshold
        status = "PASS" if ok else "FAIL ✗"
        if not ok:
            passed = False
        log.info("%-12s %8d %8d %8s", severity, count, threshold, status)

    log.info("=" * 55)
    log.info("Overall: %s", "PASS ✓" if passed else "FAIL ✗")
    log.info("=" * 55)
    return passed


def main(args: argparse.Namespace) -> None:
    summary = load_summary(Path(args.summary))
    thresholds = load_config(Path(args.config))
    passed = run_gate(summary, thresholds)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DevSecOps quality gate")
    parser.add_argument("--summary", default="reports/summary.json",
                        help="Path to consolidated summary.json")
    parser.add_argument("--config",  default="gate_config.yml",
                        help="Path to gate_config.yml with thresholds")
    main(parser.parse_args())

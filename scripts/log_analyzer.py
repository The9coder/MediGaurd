"""
scripts/log_analyzer.py – MediGuard Access Log Analyzer
=========================================================
Parses the structured JSON-line access log written by app/factory.py.
Detects repeated failed login attempts per IP (brute-force indicator).
Writes a human-readable security report to logs/security_report.txt.

Usage:
    python scripts/log_analyzer.py \\
        --log    logs/access.log \\
        --out    logs/security_report.txt \\
        --threshold 5

Log line format (JSON):
    {"ts":"2024-01-01T00:00:00Z","ip":"1.2.3.4","method":"POST",
     "path":"/login","status":401,"user":"anonymous","duration_ms":12.3}
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s",
                    level=logging.INFO, stream=sys.stdout)


def parse_log(log_path: Path) -> list[dict]:
    """
    Parse the JSON-line access log.
    Returns a list of failed-login events:
      {"ts":..., "ip":..., "user":...}
    Handles both JSON lines and older plain-text WARNING lines for compatibility.
    """
    events: list[dict] = []
    if not log_path.exists():
        log.warning("Log file not found: %s", log_path)
        return events

    with open(log_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            # Try JSON format (new format from factory.py)
            try:
                record = json.loads(line)
                if (
                    record.get("path") == "/login"
                    and record.get("method") == "POST"
                    and record.get("status") == 401
                ):
                    events.append({
                        "ts":   record.get("ts", ""),
                        "ip":   record.get("ip", "unknown"),
                        "user": record.get("user", "anonymous"),
                    })
                continue
            except json.JSONDecodeError:
                pass

            # Fallback: plain-text WARNING format
            # e.g. "2024-01-15 12:00:01,000 | WARNING | LOGIN_FAILED | ip=1.2.3.4 username=admin"
            if "LOGIN_FAILED" in line or ("status=401" in line and "/login" in line):
                import re
                ip_match = re.search(r"ip=([^\s|]+)", line)
                user_match = re.search(r"username=([^\s|]+)", line)
                ts_match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                events.append({
                    "ts":   ts_match.group(1) if ts_match else "",
                    "ip":   ip_match.group(1) if ip_match else "unknown",
                    "user": user_match.group(1) if user_match else "anonymous",
                })

    return events


def analyze(events: list[dict], threshold: int) -> dict[str, dict]:
    """
    Aggregate failed-login counts per IP.
    Returns dict of {ip: {attempts, usernames_tried}} for IPs above threshold.
    """
    counts: dict[str, int] = collections.Counter(e["ip"] for e in events)
    usernames: dict[str, set] = collections.defaultdict(set)
    for e in events:
        usernames[e["ip"]].add(e["user"])

    return {
        ip: {
            "attempts":       cnt,
            "usernames_tried": sorted(usernames[ip]),
        }
        for ip, cnt in counts.items()
        if cnt >= threshold
    }


def write_report(
    flagged: dict[str, dict],
    total_events: int,
    threshold: int,
    out_path: Path,
) -> None:
    """Write a human-readable report to out_path."""
    lines = [
        "=" * 70,
        "  MediGuard – Security Log Analysis Report",
        f"  Generated: {datetime.now().isoformat()}",
        "=" * 70,
        "",
        f"Total failed login events : {total_events}",
        f"Alert threshold per IP    : {threshold} attempts",
        f"Suspicious IPs flagged    : {len(flagged)}",
        "",
    ]

    if flagged:
        lines.append("-- Suspicious IPs --------------------------------------------------")
        for ip, info in sorted(flagged.items(), key=lambda x: -x[1]["attempts"]):
            lines += [
                "",
                f"  IP Address  : {ip}",
                f"  Attempts    : {info['attempts']}",
                f"  Usernames   : {', '.join(info['usernames_tried'])}",
                f"  Recommended : Block IP via firewall / fail2ban",
            ]
    else:
        lines.append("No suspicious IPs detected above threshold.")

    lines += [
        "",
        "=" * 70,
        "  Recommended Mitigations",
        "=" * 70,
        "  1. Integrate fail2ban / WAF to auto-block flagged IPs.",
        "  2. Enforce MFA for all clinical user accounts.",
        "  3. Rate-limit /login to <= 5 requests/minute per IP.",
        "  4. Ship logs to a SIEM (Splunk / ELK / CloudWatch) for real-time alerting.",
        "",
    ]

    report_text = "\n".join(lines)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_text, encoding="utf-8")
    print(report_text)
    log.info("Report written to: %s", out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="MediGuard access log analyzer")
    parser.add_argument("--log",       default="logs/access.log",
                        help="Path to JSON-line access log")
    parser.add_argument("--out",       default="logs/security_report.txt",
                        help="Output report path")
    parser.add_argument("--threshold", type=int, default=5,
                        help="Failed-login count per IP to trigger alert (default: 5)")
    args = parser.parse_args()

    events = parse_log(Path(args.log))
    flagged = analyze(events, args.threshold)
    write_report(flagged, len(events), args.threshold, Path(args.out))
    sys.exit(1 if flagged else 0)


if __name__ == "__main__":
    main()

"""
scripts/consolidate_reports.py – Security Report Consolidator
==============================================================
Reads JSON output from Bandit (SAST), pip-audit (SCA), Trivy (container),
and ZAP (DAST) scan reports; normalises findings to a common schema;
writes reports/summary.json and a colour-coded reports/summary.html.

Usage:
    python scripts/consolidate_reports.py \\
        --bandit   reports/bandit.json \\
        --pip-audit reports/pip-audit.json \\
        --trivy    reports/trivy.json \\
        --zap      reports/zap.json \\
        --out-dir  reports/

Output schema per finding:
    {
        "tool":     str,        # bandit | pip-audit | trivy | zap
        "severity": str,        # CRITICAL | HIGH | MEDIUM | LOW | INFO
        "title":    str,        # short description
        "location": str,        # file:line, package@version, or URL
        "details":  str,        # raw detail or CVE id
    }
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s",
                    level=logging.INFO, stream=sys.stdout)

SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]
SEVERITY_COLORS = {
    "CRITICAL": "#c0392b",
    "HIGH":     "#e67e22",
    "MEDIUM":   "#f1c40f",
    "LOW":      "#27ae60",
    "INFO":     "#2980b9",
    "UNKNOWN":  "#95a5a6",
}


# ─────────────────────────────────────────────────────────────────────────────
# Parsers – one per tool
# ─────────────────────────────────────────────────────────────────────────────

def parse_bandit(path: Path) -> list[dict[str, str]]:
    """Parse Bandit JSON report (bandit -f json -o bandit.json .)"""
    findings = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for issue in data.get("results", []):
            findings.append({
                "tool":     "bandit",
                "severity": issue.get("issue_severity", "UNKNOWN").upper(),
                "title":    issue.get("test_id", "?") + ": " + issue.get("issue_text", ""),
                "location": f"{issue.get('filename', '?')}:{issue.get('line_number', '?')}",
                "details":  issue.get("more_info", ""),
            })
    except Exception as exc:
        log.warning("Could not parse Bandit report %s: %s", path, exc)
    return findings


def parse_pip_audit(path: Path) -> list[dict[str, str]]:
    """Parse pip-audit JSON report (pip-audit -f json -o pip-audit.json)"""
    findings = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # pip-audit output: list of {name, version, vulns:[{id, description, fix_versions}]}
        for pkg in data:
            name = pkg.get("name", "?")
            version = pkg.get("version", "?")
            for vuln in pkg.get("vulns", []):
                findings.append({
                    "tool":     "pip-audit",
                    "severity": "HIGH",   # pip-audit doesn't always give severity; default HIGH
                    "title":    f"{vuln.get('id', '?')}: {name}@{version}",
                    "location": f"{name}=={version}",
                    "details":  vuln.get("description", "")[:200],
                })
    except Exception as exc:
        log.warning("Could not parse pip-audit report %s: %s", path, exc)
    return findings


def parse_trivy(path: Path) -> list[dict[str, str]]:
    """Parse Trivy JSON report (trivy fs/image --format json -o trivy.json .)"""
    findings = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        results = data.get("Results", [])
        for result in results:
            for vuln in result.get("Vulnerabilities", []):
                severity = vuln.get("Severity", "UNKNOWN").upper()
                findings.append({
                    "tool":     "trivy",
                    "severity": severity,
                    "title":    vuln.get("VulnerabilityID", "?") + ": " + vuln.get("Title", ""),
                    "location": (
                        f"{vuln.get('PkgName', '?')}@"
                        f"{vuln.get('InstalledVersion', '?')}"
                        f" (fixed: {vuln.get('FixedVersion', 'none')})"
                    ),
                    "details":  vuln.get("Description", "")[:200],
                })
    except Exception as exc:
        log.warning("Could not parse Trivy report %s: %s", path, exc)
    return findings


def parse_zap(path: Path) -> list[dict[str, str]]:
    """Parse OWASP ZAP JSON report (zap-baseline.py -J zap.json)"""
    findings = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # ZAP JSON: {"site": [{"alerts": [{riskdesc, alert, desc, instances}]}]}
        SEV_MAP = {"High": "HIGH", "Medium": "MEDIUM", "Low": "LOW", "Informational": "INFO"}
        for site in data.get("site", []):
            for alert in site.get("alerts", []):
                risk = alert.get("riskdesc", "Unknown").split(" ")[0]
                findings.append({
                    "tool":     "zap",
                    "severity": SEV_MAP.get(risk, "UNKNOWN"),
                    "title":    alert.get("alert", "?"),
                    "location": "; ".join(
                        inst.get("uri", "?")
                        for inst in alert.get("instances", [])[:3]
                    ),
                    "details":  alert.get("desc", "")[:200],
                })
    except Exception as exc:
        log.warning("Could not parse ZAP report %s: %s", path, exc)
    return findings


# ─────────────────────────────────────────────────────────────────────────────
# Consolidation
# ─────────────────────────────────────────────────────────────────────────────

def consolidate(findings: list[dict[str, str]]) -> dict[str, Any]:
    """Build the summary dict from normalised findings."""
    counts: dict[str, int] = {s: 0 for s in SEVERITY_ORDER}
    for f in findings:
        sev = f.get("severity", "UNKNOWN")
        if sev in counts:
            counts[sev] += 1
        else:
            counts["UNKNOWN"] += 1

    # Sort findings: CRITICAL → HIGH → MEDIUM → LOW → INFO → UNKNOWN
    sev_rank = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    sorted_findings = sorted(
        findings,
        key=lambda x: sev_rank.get(x.get("severity", "UNKNOWN"), 99)
    )

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_findings": len(findings),
        "counts": counts,
        "findings": sorted_findings,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HTML report
# ─────────────────────────────────────────────────────────────────────────────

def render_html(summary: dict[str, Any]) -> str:
    """Generate a colour-coded HTML summary page."""
    counts = summary["counts"]
    findings = summary["findings"]
    total = summary["total_findings"]

    badges = "".join(
        f'<span class="badge" style="background:{SEVERITY_COLORS.get(s,"#95a5a6")}">'
        f'{s}: {counts.get(s,0)}</span> '
        for s in SEVERITY_ORDER
    )

    rows = ""
    for f in findings:
        color = SEVERITY_COLORS.get(f.get("severity", "UNKNOWN"), "#95a5a6")
        rows += (
            f'<tr>'
            f'<td><code>{f.get("tool","?")}</code></td>'
            f'<td><span class="badge" style="background:{color}">{f.get("severity","?")}</span></td>'
            f'<td>{f.get("title","?")}</td>'
            f'<td><small>{f.get("location","?")}</small></td>'
            f'<td><small>{f.get("details","")}</small></td>'
            f'</tr>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>MediGuard Security Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
    h1 {{ color: #2c3e50; }}
    .badge {{ color: white; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
    table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,.2); }}
    th {{ background: #2c3e50; color: white; padding: 10px; text-align: left; }}
    td {{ padding: 8px 10px; border-bottom: 1px solid #ddd; vertical-align: top; }}
    tr:hover {{ background: #f9f9f9; }}
    .summary {{ background: white; padding: 15px; margin-bottom: 20px;
               border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,.2); }}
  </style>
</head>
<body>
  <h1>🛡️ MediGuard – Security Scan Summary</h1>
  <div class="summary">
    <p><strong>Generated:</strong> {summary["generated_at"]}</p>
    <p><strong>Total findings:</strong> {total}</p>
    <p>{badges}</p>
  </div>
  <table>
    <thead>
      <tr><th>Tool</th><th>Severity</th><th>Title</th><th>Location</th><th>Details</th></tr>
    </thead>
    <tbody>
{rows if rows else "<tr><td colspan='5'>No findings.</td></tr>"}
    </tbody>
  </table>
  <p style="margin-top:20px;color:#888;font-size:12px;">
    MediGuard DevSecOps Pipeline – Educational Portfolio Project
  </p>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_findings: list[dict[str, str]] = []

    if args.bandit and Path(args.bandit).exists():
        f = parse_bandit(Path(args.bandit))
        log.info("Bandit: %d findings", len(f))
        all_findings.extend(f)
    else:
        log.warning("Bandit report not provided or not found: %s", args.bandit)

    if args.pip_audit and Path(args.pip_audit).exists():
        f = parse_pip_audit(Path(args.pip_audit))
        log.info("pip-audit: %d findings", len(f))
        all_findings.extend(f)
    else:
        log.warning("pip-audit report not provided or not found: %s", args.pip_audit)

    if args.trivy and Path(args.trivy).exists():
        f = parse_trivy(Path(args.trivy))
        log.info("Trivy: %d findings", len(f))
        all_findings.extend(f)
    else:
        log.warning("Trivy report not provided or not found: %s", args.trivy)

    if args.zap and Path(args.zap).exists():
        f = parse_zap(Path(args.zap))
        log.info("ZAP: %d findings", len(f))
        all_findings.extend(f)
    else:
        log.warning("ZAP report not provided or not found: %s", args.zap)

    summary = consolidate(all_findings)

    # Write JSON
    json_path = out_dir / "summary.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    log.info("Written: %s (%d total findings)", json_path, summary["total_findings"])

    # Write HTML
    html_path = out_dir / "summary.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(summary))
    log.info("Written: %s", html_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Consolidate DevSecOps scan reports")
    parser.add_argument("--bandit",    default=None, help="Path to Bandit JSON report")
    parser.add_argument("--pip-audit", dest="pip_audit", default=None, help="Path to pip-audit JSON report")
    parser.add_argument("--trivy",     default=None, help="Path to Trivy JSON report")
    parser.add_argument("--zap",       default=None, help="Path to ZAP JSON report")
    parser.add_argument("--out-dir",   dest="out_dir", default="reports", help="Output directory (default: reports/)")
    main(parser.parse_args())

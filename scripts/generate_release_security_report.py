"""
Aggregate CI scan artifacts into a per-release security report.

Usage (CI):
    python scripts/generate_release_security_report.py \\
        --artifacts artifacts \\
        --out reports/release_security_report.md \\
        --json-out reports/release_security_report.json \\
        --lint success --sast failure ...
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _load_json(path: Path | None) -> dict | list | None:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _find_artifact(root: Path, name: str) -> Path | None:
    matches = list(root.rglob(name))
    return matches[0] if matches else None


def _bandit_summary(data: dict | None) -> dict:
    if not data:
        return {"high": 0, "medium": 0, "low": 0, "findings": []}
    metrics = data.get("metrics", {})
    results = data.get("results", [])
    findings = [
        {
            "severity": r.get("issue_severity"),
            "confidence": r.get("issue_confidence"),
            "file": r.get("filename"),
            "line": r.get("line_number"),
            "issue": r.get("issue_text"),
            "test_id": r.get("test_id"),
        }
        for r in results
    ]
    return {
        "high": int(metrics.get("_totals", {}).get("SEVERITY.HIGH", 0)),
        "medium": int(metrics.get("_totals", {}).get("SEVERITY.MEDIUM", 0)),
        "low": int(metrics.get("_totals", {}).get("SEVERITY.LOW", 0)),
        "findings": findings,
    }


def _pip_audit_summary(data: list | None) -> dict:
    if not data:
        return {"cve_count": 0, "vulnerabilities": []}
    vulns = []
    for dep in data:
        for v in dep.get("vulns", []):
            vulns.append(
                {
                    "package": dep.get("name"),
                    "version": dep.get("version"),
                    "id": v.get("id"),
                    "fix_versions": v.get("fix_versions", []),
                }
            )
    return {"cve_count": len(vulns), "vulnerabilities": vulns}


def _trivy_summary(data: dict | None) -> dict:
    if not data:
        return {"critical": 0, "high": 0, "medium": 0, "low": 0}
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for result in data.get("Results", []) or []:
        for vuln in result.get("Vulnerabilities", []) or []:
            sev = vuln.get("Severity", "UNKNOWN")
            if sev in counts:
                counts[sev] += 1
    return {
        "critical": counts["CRITICAL"],
        "high": counts["HIGH"],
        "medium": counts["MEDIUM"],
        "low": counts["LOW"],
    }


def _zap_summary(data: dict | None) -> dict:
    if not data:
        return {"high": 0, "medium": 0, "low": 0, "informational": 0}
    sites = data.get("site", [])
    if isinstance(sites, dict):
        sites = [sites]
    counts = {"High": 0, "Medium": 0, "Low": 0, "Informational": 0}
    for site in sites:
        for alert in site.get("alerts", []) or []:
            risk = alert.get("riskdesc", "").split(" ", 1)[0]
            if risk in counts:
                counts[risk] += 1
    return {
        "high": counts["High"],
        "medium": counts["Medium"],
        "low": counts["Low"],
        "informational": counts["Informational"],
    }


def _gate_rows(job_results: dict[str, str]) -> list[dict]:
    labels = {
        "lint": "Lint (flake8)",
        "sast": "SAST (Bandit)",
        "sca": "Dependency SCA (pip-audit)",
        "secrets": "Secret scan (Gitleaks)",
        "tests": "Unit tests + coverage",
        "container": "Container scan (Trivy)",
        "dast": "DAST (OWASP ZAP)",
    }
    rows = []
    for key, label in labels.items():
        status = job_results.get(key, "skipped")
        rows.append({"gate": label, "status": status.upper(), "passed": status == "success"})
    return rows


def build_report(
    artifacts_dir: Path,
    job_results: dict[str, str],
) -> tuple[dict, str]:
    bandit = _bandit_summary(_load_json(_find_artifact(artifacts_dir, "bandit.json")))
    sca = _pip_audit_summary(_load_json(_find_artifact(artifacts_dir, "pip-audit.json")))
    trivy = _trivy_summary(_load_json(_find_artifact(artifacts_dir, "trivy.json")))
    zap = _zap_summary(_load_json(_find_artifact(artifacts_dir, "zap.json")))
    gates = _gate_rows(job_results)

    all_passed = all(g["passed"] for g in gates)
    severity_totals = {
        "sast_high": bandit["high"],
        "sast_medium": bandit["medium"],
        "sca_cves": sca["cve_count"],
        "container_critical": trivy["critical"],
        "container_high": trivy["high"],
        "dast_high": zap["high"],
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_decision": "PASS" if all_passed else "FAIL",
        "summary": (
            "All DevSecOps gates passed; release may proceed."
            if all_passed
            else "One or more security gates failed; release is blocked."
        ),
        "gates": gates,
        "severity_counts": severity_totals,
        "sast": bandit,
        "dependency_sca": sca,
        "container": trivy,
        "dast": zap,
        "remediation_notes": [
            "Keep patient identifiers parameterised in app/routes/patients.py.",
            "Provide strong production secrets through the deployment secret store.",
            "Run pip-audit regularly and keep dependencies patched.",
            "Keep detailed exception information in server-side logs only.",
        ],
    }

    md_lines = [
        "# MediGuard – Release Security Report",
        "",
        f"**Generated (UTC):** {payload['generated_at']}",
        f"**Release decision:** **{payload['release_decision']}**",
        "",
        payload["summary"],
        "",
        "## Gate summary",
        "",
        "| Gate | Status |",
        "|------|--------|",
    ]
    for g in gates:
        md_lines.append(f"| {g['gate']} | {g['status']} |")

    md_lines += [
        "",
        "## Severity counts",
        "",
        f"- Bandit HIGH: **{bandit['high']}** (Medium: {bandit['medium']}, Low: {bandit['low']})",
        f"- pip-audit CVEs: **{sca['cve_count']}**",
        f"- Trivy CRITICAL/HIGH: **{trivy['critical']}** / **{trivy['high']}**",
        f"- ZAP HIGH alerts: **{zap['high']}**",
        "",
        "## Top SAST findings",
        "",
    ]
    if bandit["findings"]:
        for f in bandit["findings"][:10]:
            md_lines.append(
                f"- [{f['severity']}] `{f['file']}:{f['line']}` – {f['issue']} ({f['test_id']})"
            )
    else:
        md_lines.append("- (No Bandit report artifact found.)")

    md_lines += [
        "",
        "## Known demo vulnerabilities (fix before production)",
        "",
    ]
    for note in payload["remediation_notes"]:
        md_lines.append(f"- {note}")

    return payload, "\n".join(md_lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", default="artifacts")
    parser.add_argument("--out", default="reports/release_security_report.md")
    parser.add_argument("--json-out", default="reports/release_security_report.json")
    for gate in ("lint", "sast", "sca", "secrets", "tests", "container", "dast"):
        parser.add_argument(f"--{gate}", default="skipped")
    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts)
    job_results = {
        "lint": args.lint,
        "sast": args.sast,
        "sca": args.sca,
        "secrets": args.secrets,
        "tests": args.tests,
        "container": args.container,
        "dast": args.dast,
    }

    payload, markdown = build_report(artifacts_dir, job_results)

    out_path = Path(args.out)
    json_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()

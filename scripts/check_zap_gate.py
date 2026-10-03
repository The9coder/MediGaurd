"""Fail CI when OWASP ZAP baseline reports HIGH (or High) risk alerts."""
import json
import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "reports/zap.json")
    if not path.is_file():
        print(f"[ZAP GATE] Missing report: {path} — treating as failure.")
        return 1

    data = json.loads(path.read_text(encoding="utf-8"))
    sites = data.get("site", [])
    if isinstance(sites, dict):
        sites = [sites]

    high = 0
    for site in sites:
        for alert in site.get("alerts", []) or []:
            risk = (alert.get("riskdesc") or "").lower()
            if risk.startswith("high"):
                high += 1

    print(f"[ZAP GATE] HIGH alerts: {high}")
    if high > 0:
        print("[ZAP GATE] FAIL – resolve HIGH findings before release.")
        return 1
    print("[ZAP GATE] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

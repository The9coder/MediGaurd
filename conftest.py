"""
Root-level conftest.py — applied before any test module is collected.

Compatibility shim: MarkupSafe ≥ 2.1 removed `soft_unicode`; Jinja2 2.x
still imports it. This adds the alias so Flask 1.1.4 / Jinja2 2.11.3 can
coexist with modern MarkupSafe on Python 3.11+.

NOTE: This shim only exists because requirements.txt intentionally pins an
old Flask to demonstrate a vulnerable dependency (CVE-2023-30861).
In a production fix, you would upgrade Flask instead.
"""
import markupsafe

if not hasattr(markupsafe, "soft_unicode"):
    markupsafe.soft_unicode = markupsafe.soft_str  # type: ignore[attr-defined]

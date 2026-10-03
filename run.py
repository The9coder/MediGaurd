"""
MediGuard entry point
"""
import os

# Compatibility shim: MarkupSafe ≥ 2.1 removed soft_unicode;
# Jinja2 2.x (paired with Flask 1.1.4 CVE-demo pin) still imports it.
import markupsafe
if not hasattr(markupsafe, "soft_unicode"):
    markupsafe.soft_unicode = markupsafe.soft_str  # type: ignore[attr-defined]

from app.factory import create_app

app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

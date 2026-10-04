"""Session authentication helpers for OIDC-authenticated users."""

import functools

from flask import jsonify, request, session


def auth_required(view):
    """Require a valid identity established by the OIDC callback."""

    @functools.wraps(view)
    def decorated(*args, **kwargs):
        principal = session.get("principal")
        if (
            not isinstance(principal, dict)
            or not isinstance(principal.get("sub"), str)
            or principal.get("role") not in {"admin", "clinician"}
        ):
            return jsonify({"error": "Authentication required"}), 401
        request.principal = principal
        return view(*args, **kwargs)

    return decorated

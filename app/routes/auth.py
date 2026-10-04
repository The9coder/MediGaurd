"""OIDC login and browser-session endpoints."""

import logging
import secrets

from authlib.integrations.base_client.errors import OAuthError
from flask import Blueprint, current_app, jsonify, redirect, session, url_for
from psycopg import Error as DatabaseError
from psycopg_pool import PoolTimeout

from app.database import get_db, write_audit
from app.extensions import limiter

auth_bp = Blueprint("auth", __name__)
access_logger = logging.getLogger("mediguard.access")


@auth_bp.get("/auth/login")
@limiter.limit("10 per minute")
def login():
    oidc = current_app.extensions.get("oidc_client")
    if oidc is None:
        return jsonify({"error": "Identity provider is not configured"}), 503
    return oidc.authorize_redirect(url_for("auth.callback", _external=True))


@auth_bp.get("/auth/callback")
@limiter.limit("20 per minute")
def callback():
    oidc = current_app.extensions.get("oidc_client")
    if oidc is None:
        return jsonify({"error": "Identity provider is not configured"}), 503

    try:
        token = oidc.authorize_access_token()
    except OAuthError as error:
        current_app.logger.warning("OIDC authorization failed (%s)", type(error).__name__)
        return jsonify({"error": "Sign-in could not be completed"}), 401

    claims = token.get("userinfo")
    if not isinstance(claims, dict):
        try:
            claims = oidc.userinfo(token=token)
        except OAuthError as error:
            current_app.logger.warning(
                "OIDC user information request failed (%s)", type(error).__name__
            )
            return jsonify({"error": "Sign-in could not be completed"}), 401

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        current_app.logger.error("OIDC response did not include a valid subject")
        return jsonify({"error": "Identity provider returned an invalid identity"}), 401

    role_claim = claims.get(current_app.config["OIDC_ROLE_CLAIM"], [])
    if isinstance(role_claim, str):
        roles = {role_claim}
    elif isinstance(role_claim, list) and all(isinstance(role, str) for role in role_claim):
        roles = set(role_claim)
    else:
        roles = set()
    role = "admin" if current_app.config["OIDC_ADMIN_ROLE"] in roles else "clinician"

    session.clear()
    current_app.session_interface.regenerate(session)
    session.permanent = True
    session["principal"] = {"sub": subject, "role": role}
    session["csrf_token"] = secrets.token_urlsafe(32)
    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor()
        write_audit(cursor, "auth.login", "session")
        db.commit()
    except (DatabaseError, PoolTimeout) as error:
        if db is not None:
            db.rollback()
        session.clear()
        current_app.logger.error("OIDC login audit failed (%s)", type(error).__name__)
        return jsonify({"error": "Sign-in service is temporarily unavailable"}), 503
    finally:
        if cursor is not None:
            cursor.close()
    access_logger.info("OIDC_LOGIN_SUCCESS role=%s", role)
    return redirect("/")


@auth_bp.get("/auth/session")
def session_info():
    principal = session.get("principal")
    if not isinstance(principal, dict):
        return jsonify({"authenticated": False}), 200
    return jsonify(
        {
            "authenticated": True,
            "role": principal.get("role"),
            "csrf_token": session["csrf_token"],
        }
    ), 200


@auth_bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify({"authenticated": False}), 200

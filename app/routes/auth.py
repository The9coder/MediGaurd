"""
/register and /login – create accounts and issue JWTs
"""
import logging
import re

from flask import Blueprint, current_app, jsonify, request
from mysql.connector import IntegrityError, Error as MySQLError
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth import generate_token
from app.database import ensure_app_tables, get_db

auth_bp = Blueprint("auth", __name__)
access_logger = logging.getLogger("access")

# Built-in demo accounts are retained for local demonstrations.
DEMO_USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "clinician": {"password": "clinic456", "role": "clinician"},
}


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")

    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_-]{3,50}", username):
        return jsonify({
            "error": "Username must be 3-50 characters using letters, numbers, _ or -"
        }), 400
    if not isinstance(password, str) or len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if username in DEMO_USERS:
        return jsonify({"error": "Username is already taken"}), 409

    db = get_db()
    cursor = db.cursor()
    try:
        ensure_app_tables(cursor)
        cursor.execute(
            "INSERT INTO app_users (username, password_hash, role) VALUES (%s, %s, %s)",
            (username, generate_password_hash(password), "clinician"),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        return jsonify({"error": "Username is already taken"}), 409
    except MySQLError:
        db.rollback()
        current_app.logger.exception("Account registration failed")
        return jsonify({"error": "Account service is temporarily unavailable"}), 503
    finally:
        cursor.close()

    token = generate_token(username, "clinician")
    return jsonify({"token": token, "role": "clinician", "username": username}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")
    ip = request.remote_addr

    if (
        not isinstance(username, str)
        or not username
        or not isinstance(password, str)
        or not password
    ):
        return jsonify({"error": "Invalid credentials"}), 401

    user = DEMO_USERS.get(username)
    if user:
        if user["password"] != password:
            access_logger.warning("LOGIN_FAILED | ip=%s username=%s", ip, username)
            return jsonify({"error": "Invalid credentials"}), 401
        token = generate_token(username, user["role"])
        access_logger.info("LOGIN_SUCCESS | ip=%s username=%s", ip, username)
        return jsonify({"token": token, "role": user["role"]}), 200

    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        ensure_app_tables(cursor)
        cursor.execute(
            "SELECT username, password_hash, role FROM app_users WHERE username = %s",
            (username,),
        )
        stored_user = cursor.fetchone()
    except MySQLError:
        current_app.logger.exception("Account login lookup failed")
        return jsonify({"error": "Account service is temporarily unavailable"}), 503
    finally:
        cursor.close()

    if not stored_user or not check_password_hash(stored_user["password_hash"], password):
        access_logger.warning("LOGIN_FAILED | ip=%s username=%s", ip, username)
        return jsonify({"error": "Invalid credentials"}), 401

    token = generate_token(stored_user["username"], stored_user["role"])
    access_logger.info("LOGIN_SUCCESS | ip=%s username=%s", ip, username)
    return jsonify({"token": token, "role": stored_user["role"]}), 200

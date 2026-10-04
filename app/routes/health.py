"""
/health  – liveness / readiness probe
"""
from flask import Blueprint, current_app, jsonify, render_template
from psycopg import Error as DatabaseError
from redis.exceptions import RedisError

from app.database import get_db

health_bp = Blueprint("health", __name__)


@health_bp.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@health_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "mediguard-api", "version": "1.0.0"}), 200


@health_bp.route("/ready", methods=["GET"])
def readiness():
    try:
        cursor = get_db().cursor()
        try:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        finally:
            cursor.close()
        if current_app.config["REDIS_URL"] != "memory://":
            current_app.config["SESSION_REDIS"].ping()
    except (DatabaseError, RedisError) as error:
        current_app.logger.error("Readiness dependency check failed (%s)", type(error).__name__)
        return jsonify({"status": "unavailable"}), 503
    return jsonify({"status": "ready"}), 200

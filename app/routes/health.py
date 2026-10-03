"""
/health  – liveness / readiness probe
"""
from flask import Blueprint, jsonify, render_template

health_bp = Blueprint("health", __name__)


@health_bp.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@health_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "mediguard-api", "version": "1.0.0"}), 200

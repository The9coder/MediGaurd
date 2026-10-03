"""JWT-protected patient records."""
import re
import secrets
from datetime import date

from flask import Blueprint, current_app, jsonify, request
from mysql.connector import IntegrityError, Error as MySQLError

from app.auth import jwt_required
from app.database import get_db

patients_bp = Blueprint("patients", __name__)
PATIENT_FIELDS = (
    "id, name, dob, gender, mrn, diagnosis, assigned_to, created_at"
)


def _patient_scope():
    payload = request.jwt_payload
    if payload.get("role") == "admin":
        return "", ()
    return " WHERE assigned_to = %s", (payload["sub"],)


def _patient_query_base():
    return f"SELECT {PATIENT_FIELDS} FROM patients"


@patients_bp.route("/patients", methods=["GET", "POST"])
@jwt_required
def patients():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        dob = data.get("dob")
        gender = data.get("gender")
        diagnosis = data.get("diagnosis", "")

        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 150:
            return jsonify({"error": "Name is required and must be 150 characters or fewer"}), 400
        if not isinstance(dob, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dob):
            return jsonify({"error": "Date of birth must use YYYY-MM-DD format"}), 400
        try:
            date.fromisoformat(dob)
        except ValueError:
            return jsonify({"error": "Date of birth is not a valid calendar date"}), 400
        if gender not in ("M", "F", "O"):
            return jsonify({"error": "Gender must be M, F, or O"}), 400
        if not isinstance(diagnosis, str) or len(diagnosis) > 255:
            return jsonify({"error": "Diagnosis must be 255 characters or fewer"}), 400

        username = request.jwt_payload["sub"]
        mrn = f"MG-{secrets.token_hex(5).upper()}"
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute(
                "INSERT INTO patients (name, dob, gender, mrn, diagnosis, assigned_to) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (name.strip(), dob, gender, mrn, diagnosis.strip(), username),
            )
            patient_id = cursor.lastrowid
            db.commit()
        except IntegrityError:
            db.rollback()
            current_app.logger.exception("Patient record could not be saved")
            return jsonify({"error": "Unable to save patient record; please retry"}), 409
        except MySQLError:
            db.rollback()
            current_app.logger.exception("Patient record insert failed")
            return jsonify({"error": "Patient record service is temporarily unavailable"}), 503
        finally:
            cursor.close()

        return jsonify({"id": patient_id, "mrn": mrn}), 201

    scope, params = _patient_scope()
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        if scope:
            query = f"{_patient_query_base()} {scope} ORDER BY id ASC"
        else:
            query = f"{_patient_query_base()} ORDER BY id ASC"
        cursor.execute(query, params)
        records = cursor.fetchall()
    except MySQLError:
        current_app.logger.exception("Patient list query failed")
        return jsonify({"error": "Patient records are temporarily unavailable"}), 503
    finally:
        cursor.close()

    return jsonify({"patients": records}), 200


@patients_bp.route("/patients/<patient_id>", methods=["GET"])
@jwt_required
def get_patient(patient_id):
    scope, params = _patient_scope()
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        # INTENTIONAL VULNERABILITY #1: patient_id is interpolated into SQL.
        # Keep this unsafe only in the educational baseline; bind it as a
        # parameter in the remediation fork.
        if params:
            query = f"{_patient_query_base()} WHERE id = {patient_id} AND assigned_to = %s"
        else:
            query = f"{_patient_query_base()} WHERE id = {patient_id}"
        cursor.execute(query, params)
        patient = cursor.fetchone()
    except MySQLError:
        current_app.logger.exception("Patient lookup failed")
        return jsonify({"error": "Patient records are temporarily unavailable"}), 503
    finally:
        cursor.close()

    if not patient:
        return jsonify({"error": "Patient not found"}), 404
    return jsonify(patient), 200

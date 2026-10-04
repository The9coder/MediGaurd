"""OIDC-authenticated, subject-scoped patient records."""
import re
import secrets
from datetime import date

from flask import Blueprint, current_app, jsonify, request
from psycopg import IntegrityError, Error as DatabaseError

from app.auth import auth_required
from app.database import get_db, write_audit

patients_bp = Blueprint("patients", __name__)


def _patient_scope():
    payload = request.principal
    if payload.get("role") == "admin":
        return False, ()
    return True, (payload["sub"],)


@patients_bp.route("/patients", methods=["GET", "POST"])
@auth_required
def patients():
    if (
        current_app.config.get("DEPLOYMENT_ENV") == "production"
        and not current_app.config["ENABLE_PATIENT_RECORDS"]
    ):
        return jsonify({
            "error": "Patient-record service is not enabled for this deployment"
        }), 503
    if request.method == "POST":
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400
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

        username = request.principal["sub"]
        mrn = f"MG-{secrets.token_hex(5).upper()}"
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute(
                "INSERT INTO patients (name, dob, gender, mrn, diagnosis, assigned_to) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (name.strip(), dob, gender, mrn, diagnosis.strip(), username),
            )
            patient_id = cursor.fetchone()["id"]
            write_audit(cursor, "patient.create", "patient", patient_id)
            db.commit()
        except IntegrityError as error:
            db.rollback()
            current_app.logger.warning(
                "Patient record could not be saved (%s)", error.sqlstate
            )
            return jsonify({"error": "Unable to save patient record; please retry"}), 409
        except DatabaseError as error:
            db.rollback()
            current_app.logger.error("Patient record insert failed (%s)", error.sqlstate)
            return jsonify({"error": "Patient record service is temporarily unavailable"}), 503
        finally:
            cursor.close()

        return jsonify({"id": patient_id, "mrn": mrn}), 201

    try:
        limit = int(request.args.get("limit", "100"))
        after_id = int(request.args.get("after_id", "0"))
    except ValueError:
        return jsonify({"error": "Pagination values must be integers"}), 400
    if not 1 <= limit <= 100 or after_id < 0:
        return jsonify({"error": "Pagination values are outside the allowed range"}), 400

    scoped, params = _patient_scope()
    db = get_db()
    cursor = db.cursor()
    try:
        if scoped:
            cursor.execute(
                "SELECT id, name, dob, gender, mrn, diagnosis, assigned_to, created_at "
                "FROM patients WHERE assigned_to = %s AND id > %s "
                "ORDER BY id ASC LIMIT %s",
                (*params, after_id, limit),
            )
        else:
            cursor.execute(
                "SELECT id, name, dob, gender, mrn, diagnosis, assigned_to, created_at "
                "FROM patients WHERE id > %s ORDER BY id ASC LIMIT %s",
                (after_id, limit),
            )
        records = cursor.fetchall()
        write_audit(cursor, "patient.list", "patient")
        db.commit()
    except DatabaseError as error:
        db.rollback()
        current_app.logger.error("Patient list query failed (%s)", error.sqlstate)
        return jsonify({"error": "Patient records are temporarily unavailable"}), 503
    finally:
        cursor.close()

    next_after_id = records[-1]["id"] if len(records) == limit else None
    return jsonify({"patients": records, "next_after_id": next_after_id}), 200


@patients_bp.route("/patients/<int:patient_id>", methods=["GET"])
@auth_required
def get_patient(patient_id):
    if (
        current_app.config.get("DEPLOYMENT_ENV") == "production"
        and not current_app.config["ENABLE_PATIENT_RECORDS"]
    ):
        return jsonify({
            "error": "Patient-record service is not enabled for this deployment"
        }), 503
    scoped, params = _patient_scope()
    db = get_db()
    cursor = db.cursor()
    try:
        if scoped:
            cursor.execute(
                "SELECT id, name, dob, gender, mrn, diagnosis, assigned_to, created_at "
                "FROM patients WHERE id = %s AND assigned_to = %s",
                (patient_id, *params),
            )
        else:
            cursor.execute(
                "SELECT id, name, dob, gender, mrn, diagnosis, assigned_to, created_at "
                "FROM patients WHERE id = %s",
                (patient_id,),
            )
        patient = cursor.fetchone()
        write_audit(cursor, "patient.read", "patient", patient_id)
        db.commit()
    except DatabaseError as error:
        db.rollback()
        current_app.logger.error("Patient lookup failed (%s)", error.sqlstate)
        return jsonify({"error": "Patient records are temporarily unavailable"}), 503
    finally:
        cursor.close()

    if not patient:
        return jsonify({"error": "Patient not found"}), 404
    return jsonify(patient), 200

"""
Database connection helper (MySQL via mysql-connector-python)
"""
import mysql.connector
from flask import current_app, g


def ensure_app_tables(cursor):
    """Create app-owned tables for existing installations as well as fresh DBs."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'clinician',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS prediction_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL,
            features JSON NOT NULL,
            prediction TINYINT NOT NULL,
            risk_probability DECIMAL(6, 4) NOT NULL,
            risk_label VARCHAR(10) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_prediction_username (username)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def get_db():
    """Return a per-request MySQL connection, stored in Flask's g object."""
    if "db" not in g:
        g.db = mysql.connector.connect(
            host=current_app.config["DB_HOST"],
            port=current_app.config["DB_PORT"],
            user=current_app.config["DB_USER"],
            password=current_app.config["DB_PASSWORD"],
            database=current_app.config["DB_NAME"],
        )
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None and db.is_connected():
        db.close()

"""Tests for PostgreSQL connection lifecycle helpers."""

from unittest.mock import MagicMock, patch

from flask import session

from app.database import close_db, get_db


def test_close_db_when_no_connection(app):
    with app.app_context():
        close_db()


def test_get_db_and_close_returns_connection_to_pool(app):
    mock_connection = MagicMock()
    pool = app.extensions["db_pool"]
    with patch.object(pool, "getconn", return_value=mock_connection) as getconn:
        with patch.object(pool, "putconn") as putconn:
            with app.app_context():
                first = get_db()
                second = get_db()
                assert first is second
                getconn.assert_called_once_with()
                close_db()
                putconn.assert_called_once_with(mock_connection)


def test_get_db_sets_transaction_scoped_rls_identity(app):
    connection = MagicMock()
    pool = app.extensions["db_pool"]
    with patch.object(pool, "getconn", return_value=connection):
        with patch.object(pool, "putconn"):
            with app.test_request_context("/patients"):
                session["principal"] = {"sub": "clinician-sub", "role": "clinician"}
                get_db()
                (
                    query,
                    params,
                ) = connection.cursor.return_value.__enter__.return_value.execute.call_args.args
                assert "set_config('app.subject_id'" in query
                assert params == ("clinician-sub", "clinician")
                close_db()

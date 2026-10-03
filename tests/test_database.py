"""Tests for app/database.py connection lifecycle."""
from unittest.mock import MagicMock, patch

from app.database import close_db, get_db


def test_close_db_when_no_connection(app):
    with app.app_context():
        close_db()


@patch("app.database.mysql.connector.connect")
def test_get_db_and_close(mock_connect, app):
    mock_db = MagicMock()
    mock_db.is_connected.return_value = True
    mock_connect.return_value = mock_db

    with app.app_context():
        db1 = get_db()
        db2 = get_db()
        assert db1 is db2
        close_db()
        mock_db.close.assert_called_once()

"""PostgreSQL connection and minimal audit-event helpers."""

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from flask import current_app, g, has_request_context, request, session


def init_database(app):
    """Configure a per-process connection pool; schema is managed out of band."""
    app.extensions["db_pool"] = ConnectionPool(
        conninfo=app.config["DATABASE_URL"],
        min_size=1,
        max_size=10,
        kwargs={
            "row_factory": dict_row,
            "sslmode": app.config["DB_SSLMODE"],
            "connect_timeout": 5,
        },
        open=False,
    )


def get_db():
    """Return a pooled PostgreSQL connection for the current request."""
    if "db" not in g:
        g.db = current_app.extensions["db_pool"].getconn()
        principal = session.get("principal") if has_request_context() else None
        if isinstance(principal, dict):
            with g.db.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.subject_id', %s, true), "
                    "set_config('app.role', %s, true)",
                    (principal.get("sub", ""), principal.get("role", "clinician")),
                )
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        current_app.extensions["db_pool"].putconn(db)


def write_audit(cursor, action: str, resource_type: str, resource_id=None) -> None:
    """Write a minimal audit event; never include patient values or request bodies."""
    principal = session.get("principal", {})
    cursor.execute(
        """
        INSERT INTO audit_events (actor_sub, action, resource_type, resource_id, source_ip)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            principal.get("sub", "unknown"),
            action,
            resource_type,
            str(resource_id) if resource_id is not None else None,
            request.remote_addr,
        ),
    )

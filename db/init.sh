#!/bin/sh
set -eu

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=app_user="$DB_USER" --set=app_password="$DB_PASSWORD" \
    --set=app_db="$POSTGRES_DB" <<'SQL'
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password';
\i /schema.sql
GRANT CONNECT ON DATABASE :"app_db" TO :"app_user";
GRANT USAGE ON SCHEMA public TO :"app_user";
GRANT SELECT, INSERT ON patients TO :"app_user";
GRANT USAGE, SELECT ON SEQUENCE patients_id_seq TO :"app_user";
GRANT INSERT ON audit_events TO :"app_user";
GRANT USAGE, SELECT ON SEQUENCE audit_events_id_seq TO :"app_user";
SQL

# MediGuard

MediGuard is a Flask application demonstrating OIDC authentication, PostgreSQL-backed patient records, access controls, audit events, and an optional heart-risk prediction service.

> **Not cleared for real health data or clinical use.** This repository is an engineering prototype. It has not undergone an independent security assessment, Indian DPDP compliance assessment, clinical validation, or a determination of applicable medical-device requirements. The included model is a development artifact, not a medical device. Do not deploy this repository with real patient information or use its predictions for care decisions.

## Security architecture

- **Identity:** OIDC authorization-code flow through an organization-managed provider. The provider must enforce MFA and manage user lifecycle. The provider's signed role claim grants `admin`; all other valid users receive the restricted `clinician` role.
- **Browser session:** server-side Redis sessions; short lifetime; Secure/HttpOnly/SameSite cookies in production; state-protected OIDC callback; CSRF token required for state-changing API requests. No access or refresh token is placed in browser local storage.
- **Data:** PostgreSQL with subject-scoped route checks and database row-level security. The application role is intended to have only SELECT/INSERT access to patient data and INSERT-only access to audit events. RLS is defense in depth, not a boundary against someone who has compromised the application database credential.
- **Patient-record gate:** patient routes are disabled in production by default. Enabling them requires an explicit data-governance/retention reference; this is an operator attestation, not a legal determination.
- **Audit:** minimal patient-record and prediction access/change events are written in the same database transaction as the operation. Event payloads omit names, diagnoses, and feature values. The database role cannot update or delete audit events.
- **Abuse controls:** Flask-Limiter uses Redis storage so limits are shared across workers.
- **Prediction:** disabled by default in production. Saved prediction history is disabled; inference results are returned only in the immediate response and only a minimal audit event is retained. Enabling inference requires a model artifact, matching SHA-256, and a validation-reference identifier. These settings provide an integrity gate; they do not establish clinical validity or regulatory approval.
- **Response hardening:** CSRF checks, request-size limit, secure response headers, generic server errors, endpoint-only access logs, and no-store responses.

## Routes

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/` | None | Portal |
| `GET` | `/health` | None | Liveness check |
| `GET` | `/auth/login` | None | Begin OIDC sign-in |
| `GET` | `/auth/callback` | OIDC state | Complete OIDC sign-in |
| `GET` | `/auth/session` | None | Check session and obtain CSRF token |
| `POST` | `/auth/logout` | Session + CSRF | End local session |
| `GET`, `POST` | `/patients` | Session + CSRF for POST | Cursor-paginated list/create scoped patient records |
| `GET` | `/patients/<id>` | Session | Read a scoped patient record |
| `POST` | `/predict` | Session + CSRF | Optional model inference; production-disabled by default |

The API and portal are same-origin and use the HttpOnly session cookie. JavaScript obtains a CSRF token from `/auth/session` and sends it as `X-CSRF-Token` on mutating requests.

## Local container setup

1. Create a dedicated OIDC client and register `http://localhost:5000/auth/callback` for local testing. Configure the provider to issue the `roles` claim (or set `OIDC_ROLE_CLAIM`) and assign the configured admin role only to approved operators.
2. Copy `.env.example` to `.env`, replace every placeholder, and URL-encode database and Redis passwords when placing them in URLs. Do not commit `.env`.
3. Start the local integration stack:

   ```powershell
   docker compose up --build
   ```

The sample Compose stack binds the API to `127.0.0.1:5000`, starts PostgreSQL and Redis, and disables predictions. Its local database and Redis connections are not TLS protected; it is **not a production deployment configuration**. `db/init.sh` provisions a restricted application role and initializes an empty schema on the first database-volume creation. It does not migrate an existing MySQL database or update an already-initialized PostgreSQL volume.

## Production deployment requirements

The production app factory refuses to start without explicit `SECRET_KEY`, OIDC client settings, `DATABASE_URL`, and `REDIS_URL`. It also requires a strong session key and PostgreSQL TLS (`DB_SSLMODE=verify-full` is recommended with trusted CA configuration). Production cookies are Secure; the app assumes TLS is terminated by a trusted ingress/reverse proxy. Restrict direct network access to the API and configure trusted-proxy handling at the deployment boundary.

Before any real-data deployment, an accountable team must at minimum:

1. Complete threat modeling, independent penetration testing, and remediation of findings.
2. Assess DPDP Act/rules applicability, notices/consent or other lawful basis, processor contracts, retention, data-subject request handling, breach response, and any cross-border transfers with qualified counsel.
3. Have a qualified clinical team validate the model on representative Indian populations, document intended use, performance limits, calibration, bias, human-factors, monitoring, and rollback. Obtain a legal/regulatory determination about applicable CDSCO/medical-device obligations. The current demo model must not be used.
4. Use managed PostgreSQL and Redis with TLS, private networking, encryption at rest, encrypted backups, tested restore procedures, credential rotation, monitoring, and restricted operator access.
5. Configure OIDC MFA, account provisioning/deprovisioning, role assignment, session/revocation policy, and recovery procedures in the identity provider.
6. Define audit retention, access monitoring, alerting, log access controls, incident response, and data-deletion procedures. Do not ship patient values or feature payloads to general application logs.
7. Run schema migrations through an approved privileged migration identity; keep the runtime `mediguard_app` identity non-owner and least-privileged.
8. Gate releases on CI tests, dependency scanning, SAST, secret scanning, container scanning, and independent DAST/security review.

Compose uses local PostgreSQL initialization SQL as a bootstrap illustration. For managed production services, apply the schema using a controlled migration process and verify that the runtime role is not a table owner, does not have `BYPASSRLS`, and has no UPDATE/DELETE rights over audit records. RLS policies rely on application-set PostgreSQL session parameters and do not defend against a fully compromised application credential.

### Required production settings

- `FLASK_ENV=production`
- `SECRET_KEY` (at least 32 characters, randomly generated and stored in a secret manager)
- `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`
- `OIDC_ROLE_CLAIM`, `OIDC_ADMIN_ROLE`
- `DATABASE_URL` and `DB_SSLMODE=verify-full`
- `REDIS_URL` pointing to an authenticated TLS-enabled managed Redis service
- `ENABLE_PATIENT_RECORDS=true` plus `PATIENT_DATA_GOVERNANCE_REFERENCE` only after an approved privacy and retention policy exists
- `ENABLE_PREDICTIONS=false` until all model/clinical/regulatory approvals are documented
- If predictions are approved: `MODEL_PATH`, `MODEL_SHA256`, and `MODEL_VALIDATION_REFERENCE`

Never enable `DEBUG` in production. Do not expose PostgreSQL, Redis, or the Flask/Gunicorn port directly to the public internet; use a managed ingress with TLS, access controls, and request limits.

## Tests and checks

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\flake8 app tests\test_auth.py tests\test_database.py tests\test_health.py tests\test_patients.py tests\test_predict.py tests\test_security_hardening.py tests\test_security_remediations.py
.\.venv\Scripts\bandit -r app scripts -c .bandit -ll
.\.venv\Scripts\pip-audit -r requirements.txt
```

The CI lint gate focuses on the application and security regression tests; the repository's older analysis scripts and test helpers have pre-existing style findings.

Most route tests use mocked persistence and test OIDC sessions. They do not prove that your identity provider, PostgreSQL grants/RLS, TLS, backups, or production environment are correctly configured. Validate those in a separate integration environment before any release.

# 🏥 MediGuard – Heart-Disease Prediction API with DevSecOps Integration

>**Educational Demo Project**  
MediGuard is a Flask‑based healthcare API with JWT authentication, patient record management, and machine‑learning risk prediction. It integrates Docker, CI/CD pipelines, and automated security checks to demonstrate secure API development practices.  
⚠️ All patient data is synthetic and for demonstration only. Do **not** deploy this code to production as‑is.
---

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Endpoints](#endpoints)
4. [Quick Start](#quick-start)
5. [Running Tests](#running-tests)
6. [Log Analysis](#log-analysis)
7. [Project Structure](#project-structure)
8. [DevSecOps Pipeline Stages](#devsecops-pipeline-stages)
9. [Security Remediation Status](#security-remediation-status)
10. [TODO – Replacing the Placeholder Model](#todo--replacing-the-placeholder-model)

---

## Overview

A health-tech startup exposes a **heart disease risk prediction API** to partner clinics. It handles sensitive patient records, so **no release may reach deployment without passing automated security checks**.

This project demonstrates:
- A Flask REST API with JWT authentication and MySQL-backed patient records
- A scikit-learn ML model integration (placeholder; swap in your own)
- Access logging + brute-force detection via `scripts/log_analyzer.py`
- Docker + Docker Compose for local development
- Pytest test suite with coverage
- Automated security checks and a remediation branch that demonstrates fixes

---

## Architecture

```
 Clinic Client
      │  HTTPS
      ▼
 ┌───────────────────────┐
 │   Flask API (Gunicorn)│
 │   /health             │
 │   /login  ──► JWT     │
 │   /predict ──► Model  │
 │   /patients/<id>      │
 └────────┬──────────────┘
          │ mysql-connector
          ▼
 ┌──────────────────────┐
 │   MySQL 8.0          │
 │   mediguard_db       │
 │   patients table     │
 └──────────────────────┘
          │
┌──────────────────────┐
│   logs/access.log    │──► scripts/log_analyzer.py ──► logs/security_report.txt
└──────────────────────┘
```

---

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/health` | None | Liveness / readiness probe |
| `POST` | `/login` | None | Accepts `{username, password}`, returns JWT |
| `POST` | `/predict` | Bearer JWT | Accepts 13 patient features, returns risk score |
| `GET`  | `/patients/<id>` | Bearer JWT | Returns patient record by ID |

### `/predict` – Input Features

```json
{
  "age": 55, "sex": 1, "cp": 3, "trestbps": 140, "chol": 250,
  "fbs": 0, "restecg": 1, "thalach": 150, "exang": 0,
  "oldpeak": 1.5, "slope": 2, "ca": 0, "thal": 2
}
```

### Local Demo Accounts

The built-in `admin` and `clinician` demo accounts are disabled unless you
explicitly set `DEMO_ADMIN_PASSWORD` and/or `DEMO_CLINICIAN_PASSWORD` in the
environment when running a non-production configuration. Production startup
rejects these demo accounts. Otherwise, create a clinician account with
`/register`.

### User Accounts and Saved Records

Users can create an account from the sign-in page. New accounts receive the
clinician role; an explicitly enabled non-production admin demo account can
access the full patient directory. Patient profiles created by a user are
assigned to that username and are visible to that user, while admins can view
all profiles. Successful risk predictions are saved to the user's prediction
history. Passwords for
registered accounts are stored as password hashes in MySQL.

This remains an educational demo with synthetic data and is not suitable for
real patient information or clinical use.

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+

### 1 – Generate the placeholder model

```bash
pip install scikit-learn numpy
python scripts/train_placeholder_model.py
```

### 2 – Start with Docker Compose

Copy `.env.example` to `.env`, then replace the placeholders with strong,
unique values for `SECRET_KEY`, `JWT_SECRET`, `DB_PASSWORD`, and
`MYSQL_ROOT_PASSWORD`. Production startup rejects missing app/database secrets
and app secrets shorter than 32 characters. Keep `.env` untracked.

```bash
docker-compose up --build
```

The API will be available at `http://localhost:5000`.

### 3 – Test the API manually

```bash
# Health check
curl http://localhost:5000/health

# Register a clinician account (replace the placeholder with a strong password)
curl -s -X POST http://localhost:5000/register \
  -H "Content-Type: application/json" \
  -d '{"username":"demo_clinician","password":"<strong-password>"}'

# Login
TOKEN=$(curl -s -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo_clinician","password":"<strong-password>"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Predict
curl -X POST http://localhost:5000/predict \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"age":55,"sex":1,"cp":3,"trestbps":140,"chol":250,"fbs":0,"restecg":1,"thalach":150,"exang":0,"oldpeak":1.5,"slope":2,"ca":0,"thal":2}'

# Patient lookup
curl http://localhost:5000/patients/1 \
  -H "Authorization: Bearer $TOKEN"
```

### 4 – Run without Docker (local)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt -r requirements-dev.txt
python scripts/train_placeholder_model.py
# Set env vars from .env.example, then:
python run.py
```

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Coverage report is printed to the terminal and written to `coverage.xml`.

### Test Matrix

| File | What is tested |
|------|---------------|
| `test_health.py` | `/health` status and response shape |
| `test_auth.py` | Login success, wrong password, unknown user, missing body, role |
| `test_predict.py` | Auth guard, successful prediction, missing features, invalid/expired JWT |
| `test_patients.py` | DB success/not-found (mocked), auth guard, parameterized ID lookup |
| `test_log_analyzer.py` | Log parsing, IP flagging, threshold, report generation |

---

## Log Analysis

Access logs are written to `logs/access.log`. Run the analyzer to detect brute-force attempts:

```bash
python scripts/log_analyzer.py --log logs/access.log --out logs/security_report.txt --threshold 5
```

Flags any IP with ≥ 5 failed login attempts and writes a human-readable report with recommended mitigations (fail2ban, MFA, rate-limiting, SIEM alerting).

---


## Project Structure

```
medigaurd/
├── app/
│   ├── __init__.py
│   ├── config.py          ← env-based secrets and optional local demo passwords
│   ├── factory.py         ← generic client errors; production secret checks
│   ├── auth.py            ← JWT utilities
│   ├── database.py        ← MySQL connection helper
│   ├── model/
│   │   └── README.md      ← Drop your .pkl here
│   └── routes/
│       ├── health.py
│       ├── auth.py
│       ├── predict.py
│       └── patients.py    ← parameterized patient queries
├── db/
│   └── init.sql           ← MySQL schema + fake seed data
├── logs/                  ← Runtime logs (git-ignored)
├── .github/workflows/
│   └── devsecops.yml      ← CI/CD security gates + release report
├── fixtures/
│   └── sample_access.log  ← demo log for log_analyzer.py
├── scripts/
│   ├── train_placeholder_model.py
│   ├── log_analyzer.py
│   ├── generate_release_security_report.py
│   └── check_zap_gate.py
├── tests/
│   ├── conftest.py
│   ├── test_health.py
│   ├── test_auth.py
│   ├── test_predict.py
│   ├── test_patients.py
│   └── test_log_analyzer.py
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── pytest.ini
├── requirements.txt       ← patched Flask/Werkzeug/Jinja2 versions
├── requirements-dev.txt
└── run.py
```

---

## Security Remediation Status

The `main` branch is the intentionally vulnerable learning baseline. The
`security-fixes` branch demonstrates remediation of the documented issues:

| Baseline issue | Remediation |
|---|---|
| SQL injection through patient ID | Route-constrain IDs to integers and bind them as SQL parameters in [`app/routes/patients.py`](app/routes/patients.py). |
| Committed/default secrets | Production startup requires strong environment-provided app and database secrets; optional demo passwords have no committed defaults. |
| Vulnerable Flask, Werkzeug, and Jinja2 pins | Updated versions in [`requirements.txt`](requirements.txt); continue running `pip-audit` to catch newly disclosed CVEs. |
| Error-response disclosure | The baseline already returned a generic HTTP 500 response; the remediation branch keeps that behavior and tests it. |
| Hardcoded Docker credentials | Docker Compose requires secrets from the environment or an untracked `.env` file. |

This is still an educational application, not a production-ready clinical system.
The security workflow must pass before release, and all scan results should be
reviewed rather than treating a clean scan as proof of security.

---
## DevSecOps Pipeline Stages

The following stages should be integrated into your CI/CD system (GitHub Actions, GitLab CI, Jenkins, etc.):

| Stage | Tool | Gate |
|-------|------|------|
| **SAST** | Bandit | Fail on HIGH severity findings |
| **Dependency SCA** | `pip-audit` / `safety` | Fail on known CVEs |
| **Secret Scanning** | `detect-secrets` / Gitleaks | Fail if secrets committed |
| **Container Scan** | Trivy | Fail on CRITICAL CVEs in image |
| **Unit Tests + Coverage** | pytest + pytest-cov | Fail if coverage < 80 % |
| **DAST** | OWASP ZAP (baseline) | Fail on HIGH alerts |
| **Lint / Format** | flake8, black | Fail on lint errors |

The CI workflow lives at [`.github/workflows/devsecops.yml`](.github/workflows/devsecops.yml). On every push/PR it runs all gates above, uploads scan artifacts, and writes a **release security report** (`release_security_report.md`) that blocks deployment when any gate fails.

The remediation branch is intended to pass the documented security checks. A
failed check blocks release; investigate its report and fix the underlying issue
rather than suppressing the finding.

### Run scans locally (Windows PowerShell)

```powershell
pip install -r requirements.txt -r requirements-dev.txt
python scripts/train_placeholder_model.py
flake8 app scripts tests
bandit -r app scripts -c .bandit -ll
pip-audit -r requirements.txt
python -m pytest --cov-fail-under=80
python scripts/log_analyzer.py --log fixtures/sample_access.log --out logs/security_report.txt
```

## TODO – Replacing the Placeholder Model

1. Train your real model and save it:
   ```python
   import pickle
   with open("app/model/heart_disease_model.pkl", "wb") as f:
       pickle.dump(your_trained_model, f)
   ```
2. Verify it exposes `.predict(X)` and `.predict_proba(X)` (standard sklearn interface).
3. Update `MODEL_PATH` environment variable or `app/config.py`.
4. Update the feature list in `app/routes/predict.py` → `EXPECTED_FEATURES` if your model uses different columns.
5. Remove the `scripts/train_placeholder_model.py` call from the CI pipeline once your real model artifact is stored (e.g. in S3 or DVC).

---

## License

This project is for **educational and demonstration purposes only**.  
No real patient data is used anywhere in this codebase.

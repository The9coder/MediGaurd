# 🏥 MediGuard – DevSecOps Pipeline for Heart-Disease Prediction API

> **⚠️ EDUCATIONAL / DEMO PROJECT**  
> This repository intentionally contains security vulnerabilities for teaching DevSecOps concepts. **Do NOT deploy this code to production as-is.** All patient data is entirely synthetic/fictional.

---

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Intentional Vulnerabilities](#intentional-vulnerabilities)
4. [Endpoints](#endpoints)
5. [Quick Start](#quick-start)
6. [Running Tests](#running-tests)
7. [Log Analysis](#log-analysis)
8. [DevSecOps Pipeline Stages](#devsecops-pipeline-stages)
9. [Project Structure](#project-structure)
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
- Intentional vulnerable code patterns used as teaching examples

---

## Architecture

```
 Clinic Client
      │  HTTPS
      ▼
 ┌──────────────────────┐
 │   Flask API (Gunicorn)│
 │   /health             │
 │   /login  ──► JWT     │
 │   /predict ──► Model  │
 │   /patients/<id>      │
 └────────┬─────────────┘
          │ mysql-connector
          ▼
 ┌──────────────────────┐
 │   MySQL 8.0          │
 │   mediguard_db       │
 │   patients table     │
 └──────────────────────┘
          │
 logs/access.log ──► scripts/log_analyzer.py ──► logs/security_report.txt
```

---

## Intentional Vulnerabilities

These vulnerabilities are **left in deliberately** for security demonstration purposes. Each is commented `# intentional, for demo only` in the source code.

| # | Vulnerability | File | Line / Function | Real-World Risk |
|---|---------------|------|-----------------|-----------------|
| 1 | **SQL Injection** | [`app/routes/patients.py`](app/routes/patients.py) | `GET /patients/<patient_id>` | The untrusted path value is interpolated into the SQL query, allowing an attacker to alter its predicates and potentially access records outside their assigned scope. **Fix:** validate the identifier and bind it as a parameter (`WHERE id = %s`). |
| 2 | **Hardcoded API Key** | [`app/config.py`](app/config.py) | `INTERNAL_API_KEY` | Secrets committed to version control are scraped by bots from public repos, leading to fraud or data exfiltration. **Fix:** load secrets from AWS Secrets Manager / HashiCorp Vault at runtime. |
| 3 | **Outdated Dependency (CVEs)** | [`requirements.txt`](requirements.txt) | `Flask==2.2.5`, `Werkzeug==2.2.3`, `Jinja2==3.1.2` | Flask 2.2.5 has CVE-2023-30861 (cookie path traversal). Werkzeug 2.2.3 has CVE-2023-25577 (ReDoS in multipart parser). Jinja2 3.1.2 has CVE-2024-22195 (XSS via `|urlencode`). All detectable by `pip-audit`. **Fix:** Pin to current stable releases; run SCA on every PR. |
| 4 | **Verbose Error Messages** | [`app/factory.py`](app/factory.py) | `internal_error()` handler | Stack traces expose internal file paths, library versions, and logic that attackers exploit. **Fix:** log trace server-side; return a generic `500` message to clients. |

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

### `/predict` – Example Response

```json
{
  "prediction": 1,
  "risk_probability": 0.7823,
  "risk_label": "HIGH",
  "disclaimer": "This is a machine-learning estimate only. It must be reviewed by a qualified clinician."
}
```

### Demo Credentials

| Username | Password | Role |
|----------|----------|------|
| `admin` | `admin123` | admin |
| `clinician` | `clinic456` | clinician |

### User Accounts and Saved Records

Users can create an account from the sign-in page. New accounts receive the
clinician role; only the built-in admin account can access the full patient
directory. Patient profiles created by a user are assigned to that username
and are visible to that user, while admins can view all profiles. Successful
risk predictions are saved to the user's prediction history. Passwords for
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

```bash
docker-compose up --build
```

The API will be available at `http://localhost:5000`.

### 3 – Test the API manually

```bash
# Health check
curl http://localhost:5000/health

# Login
TOKEN=$(curl -s -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"username":"clinician","password":"clinic456"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

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
| `test_patients.py` | DB success/not-found (mocked), auth guard, SQLi demo assertion |
| `test_log_analyzer.py` | Log parsing, IP flagging, threshold, report generation |

---

## Log Analysis

Access logs are written to `logs/access.log`. Run the analyzer to detect brute-force attempts:

```bash
python scripts/log_analyzer.py --log logs/access.log --out logs/security_report.txt --threshold 5
```

Flags any IP with ≥ 5 failed login attempts and writes a human-readable report with recommended mitigations (fail2ban, MFA, rate-limiting, SIEM alerting).

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

### Expected CI behaviour (demo vulnerabilities)

With intentional flaws still present, these gates **should fail** until you remediate them:

| Gate | Why it fails on the demo code |
|------|-------------------------------|
| Bandit (SAST) | SQL injection pattern in `patients.py` |
| pip-audit (SCA) | Pinned vulnerable Flask / Werkzeug / Jinja2 |
| Gitleaks | Hardcoded `INTERNAL_API_KEY` in `config.py` |
| OWASP ZAP (DAST) | Verbose stack traces, missing security headers, etc. |

Unit tests and the log analyzer should **pass**. After fixing vulnerabilities, re-run the workflow to obtain a green `release_decision: PASS` report.

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

---

## Project Structure

```
medigaurd/
├── app/
│   ├── __init__.py
│   ├── config.py          ← ⚠️  VULN #2 – hardcoded API key
│   ├── factory.py         ← ⚠️  VULN #4 – verbose error handler
│   ├── auth.py            ← JWT utilities
│   ├── database.py        ← MySQL connection helper
│   ├── model/
│   │   └── README.md      ← Drop your .pkl here
│   └── routes/
│       ├── health.py
│       ├── auth.py
│       ├── predict.py
│       └── patients.py    ← ⚠️  VULN #1 – SQL injection
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
├── requirements.txt       ← ⚠️  VULN #3 – outdated Flask/Werkzeug
├── requirements-dev.txt
└── run.py
```

---

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

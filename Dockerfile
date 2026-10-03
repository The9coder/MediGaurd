# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user for least-privilege execution
RUN groupadd -r mediguard && useradd -r -g mediguard mediguard

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY app/       ./app/
COPY run.py     .
COPY scripts/   ./scripts/

# Train placeholder ML model at build time (artifact is git-ignored locally)
RUN mkdir -p app/model logs \
    && python scripts/train_placeholder_model.py \
    && chown -R mediguard:mediguard /app

USER mediguard

ENV FLASK_ENV=production \
    LOG_FILE=/app/logs/access.log \
    MODEL_PATH=/app/app/model/heart_disease_model.pkl

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", "run:app"]

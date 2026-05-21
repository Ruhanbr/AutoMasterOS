# ─── Base Stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    libxml2-dev \
    libxslt-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ─── Dependencies Stage ───────────────────────────────────────────────────────
FROM base AS dependencies

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ─── Development Stage ────────────────────────────────────────────────────────
FROM dependencies AS development

COPY . .

RUN mkdir -p /storage/xml /storage/danfe /certs

EXPOSE 8000

# ─── Production Stage ─────────────────────────────────────────────────────────
FROM dependencies AS production

COPY . .

RUN mkdir -p /storage/xml /storage/danfe /certs && \
    addgroup --system automaster && \
    adduser --system --group automaster && \
    chown -R automaster:automaster /app /storage

USER automaster

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

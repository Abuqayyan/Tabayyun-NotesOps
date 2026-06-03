FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps (build essentials for some Python wheels; curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cache layer)
COPY requirements.txt /app/requirements.txt
RUN pip install --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ -r /app/requirements.txt

# Copy source
COPY . /app

# Persistent upload directory (mount as a volume in compose)
ENV UPLOAD_DIR=/data/uploads
RUN mkdir -p /data/uploads

# Run as a non-root user (Phase 0 hardening). Ensure app + data dirs are writable.
RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8001/api/ || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]

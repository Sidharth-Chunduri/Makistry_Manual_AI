FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# OS libs you were getting via the Paketo apt buildpack
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 \
      libglu1-mesa \
      libxext6 \
      libsm6 \
      libxrender1 \
      build-essential \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir gunicorn uvicorn

# Copy the rest of your app
COPY . .

# Healthcheck hits your FastAPI /api/healthz
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:${PORT}/api/healthz || exit 1

EXPOSE 8080
CMD ["/bin/sh", "-c", "exec gunicorn -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-2} -b 0.0.0.0:${PORT:-8080} app.main:app"]
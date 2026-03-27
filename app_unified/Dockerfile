# ── Stage 1: Build ──────────────────────────────────────────
# Compile dlib once here; runtime stage copies the result directly
FROM python:3.11-bullseye AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ make git \
    libopenblas-dev liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

ENV CC=/usr/bin/gcc
ENV CXX=/usr/bin/g++

# Use pip cmake (pre-built binary) — avoids system cmake version issues
RUN pip install --no-cache-dir cmake
RUN pip install --no-cache-dir dlib==19.24.2 face_recognition numpy Pillow

# ── Stage 2: Runtime ─────────────────────────────────────────
# No build tools needed — dlib is already compiled
FROM python:3.11-slim

LABEL "language"="python"
LABEL "framework"="flask"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libopenblas0 liblapack3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy pre-compiled packages from builder (no recompilation)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Install remaining deps (dlib already satisfied by COPY above)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

ENV PYTHONUNBUFFERED=1
ENV SESSION_COOKIE_SECURE=true

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--preload", "-c", "gunicorn.conf.py", "wsgi:app"]

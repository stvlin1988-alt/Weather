# ── Stage 1: Build ──────────────────────────────────────────
# Only compile dlib here — everything else installs normally in runtime
FROM python:3.11-bullseye AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ make cmake git \
    libopenblas-dev liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir setuptools wheel cmake

# Compile dlib only — multi-core build to avoid timeout
RUN CC=gcc CXX=g++ DLIB_NO_GUI_SUPPORT=1 MAKEFLAGS="-j$(nproc)" \
    pip install --no-cache-dir dlib==19.24.2

# ── Stage 2: Runtime ─────────────────────────────────────────
FROM python:3.11-slim

LABEL "language"="python"
LABEL "framework"="flask"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libopenblas0 liblapack3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only pre-compiled dlib from builder (avoids metadata conflicts)
COPY --from=builder /usr/local/lib/python3.11/site-packages/dlib \
                    /usr/local/lib/python3.11/site-packages/dlib
COPY --from=builder /usr/local/lib/python3.11/site-packages/dlib-19.24.2.dist-info \
                    /usr/local/lib/python3.11/site-packages/dlib-19.24.2.dist-info

# Install all other packages normally — face_recognition_models gets proper metadata
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

ENV PYTHONUNBUFFERED=1
ENV SESSION_COOKIE_SECURE=true

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--preload", "-c", "gunicorn.conf.py", "wsgi:app"]

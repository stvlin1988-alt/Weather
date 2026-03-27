# ── Stage 1: Build (cached by Zeabur if dlib install line unchanged) ─────
FROM python:3.11-bullseye AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ make cmake git \
    libopenblas-dev liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir setuptools wheel cmake

# Inline CC/CXX so cmake detects compilers; DLIB_NO_GUI_SUPPORT=1 avoids X11
# MAKEFLAGS="-j$(nproc)" enables parallel compilation to save time
RUN CC=gcc CXX=g++ DLIB_NO_GUI_SUPPORT=1 MAKEFLAGS="-j$(nproc)" \
    pip install --no-cache-dir "dlib>=19.24.4"

# ── Stage 2: Runtime (no build tools, no recompile) ──────────────────────
FROM python:3.11-slim

LABEL "language"="python"
LABEL "framework"="flask"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libopenblas0 \
    liblapack3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only compiled dlib from builder — avoids recompile on every deploy
COPY --from=builder /usr/local/lib/python3.11/site-packages/dlib \
                    /usr/local/lib/python3.11/site-packages/dlib
COPY --from=builder /usr/local/lib/python3.11/site-packages/dlib-*.dist-info \
                    /usr/local/lib/python3.11/site-packages/

# Build context is repo root — must use app_unified/ prefix
COPY app_unified/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY app_unified/ .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

ENV PYTHONUNBUFFERED=1
ENV SESSION_COOKIE_SECURE=true

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--preload", "-c", "gunicorn.conf.py", "wsgi:app"]

# ── Stage 1: Build ──────────────────────────────────────────
# Compile dlib once; runtime stage copies result directly (no recompilation)
FROM python:3.11-bullseye AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ make cmake git \
    libopenblas-dev liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# Install build tools via pip (ensures cmake is in PATH for dlib)
RUN pip install --no-cache-dir setuptools wheel cmake

# Inline CC/CXX/DLIB_NO_GUI_SUPPORT in the RUN command
# — ENV alone is not always inherited by pip subprocesses
RUN CC=gcc CXX=g++ DLIB_NO_GUI_SUPPORT=1 \
    pip install --no-cache-dir dlib==19.24.2 face_recognition numpy Pillow

# ── Stage 2: Runtime ─────────────────────────────────────────
# No build tools needed — packages are already compiled above
FROM python:3.11-slim

LABEL "language"="python"
LABEL "framework"="flask"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libopenblas0 liblapack3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy pre-compiled packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Install remaining deps (dlib already present from COPY above — pip skips it)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

ENV PYTHONUNBUFFERED=1
ENV SESSION_COOKIE_SECURE=true

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--preload", "-c", "gunicorn.conf.py", "wsgi:app"]

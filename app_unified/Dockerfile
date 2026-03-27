FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git libopenblas-dev liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Pre-compile dlib and face_recognition in builder stage
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir dlib face_recognition numpy Pillow

# Stage 2: Runtime image
FROM python:3.11-slim

LABEL "language"="python"
LABEL "framework"="flask"

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake libgomp1 libopenblas0 liblapack3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy compiled packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy requirements and install remaining deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY . .

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

ENV PYTHONUNBUFFERED=1
ENV SESSION_COOKIE_SECURE=true

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--preload", "-c", "gunicorn.conf.py", "wsgi:app"]

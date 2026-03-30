FROM python:3.12-slim

LABEL "language"="python"
LABEL "framework"="flask"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libopenblas0 \
    liblapack3 \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pre-built dlib wheel — no compilation needed
COPY app_unified/wheels/ /tmp/wheels/
RUN pip install --no-cache-dir --no-deps /tmp/wheels/dlib-*.whl && rm -rf /tmp/wheels

# Build context is repo root — must use app_unified/ prefix
COPY app_unified/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY app_unified/ .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

ENV PYTHONUNBUFFERED=1
ENV SESSION_COOKIE_SECURE=true

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 120 --preload -c gunicorn.conf.py wsgi:app"]

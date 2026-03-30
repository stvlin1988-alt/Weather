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

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Pre-built dlib wheel — no compilation needed
COPY app_unified/wheels/ /tmp/wheels/
RUN pip install --no-cache-dir --no-deps /tmp/wheels/dlib-*.whl && rm -rf /tmp/wheels

# face_recognition_models 必須從 git 安裝（PyPI 版本不完整）
RUN pip install --no-cache-dir git+https://github.com/ageitgey/face_recognition_models

# Build context is repo root — must use app_unified/ prefix
COPY app_unified/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app_unified/ .

# 驗證 face_recognition models 可正確載入
RUN python -c "import face_recognition; print('face_recognition models loaded successfully')" || true

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app && \
    chown -R appuser:appuser /usr/local/lib/python3.12/site-packages && \
    chown -R appuser:appuser /root/.cache 2>/dev/null || true
USER appuser

EXPOSE 8080

ENV PYTHONUNBUFFERED=1
ENV SESSION_COOKIE_SECURE=true

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 120 --preload --access-logfile - -c gunicorn.conf.py wsgi:app"]

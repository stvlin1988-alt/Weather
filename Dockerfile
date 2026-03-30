FROM python:3.12-slim

LABEL "language"="python"
LABEL "framework"="flask"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libopenblas0 \
    liblapack3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Pre-built wheels — no compilation, no git needed
COPY app_unified/wheels/ /tmp/wheels/
RUN pip install --no-cache-dir --no-deps /tmp/wheels/*.whl && rm -rf /tmp/wheels

# Build context is repo root — must use app_unified/ prefix
COPY app_unified/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 確保 setuptools 存在（face_recognition_models 需要 pkg_resources）
RUN pip install --no-cache-dir setuptools && python -c "import pkg_resources; print('pkg_resources OK')"

COPY app_unified/ .

# 驗證 wheels 已安裝（face_recognition 需要 pkg_resources shim，在 wsgi.py 提供）
RUN python -c "import dlib; print('dlib OK')"

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app && \
    chown -R appuser:appuser /usr/local/lib/python3.12/site-packages
USER appuser

EXPOSE 8080

ENV PYTHONUNBUFFERED=1
ENV SESSION_COOKIE_SECURE=true

CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]

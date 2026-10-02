# syntax=docker/dockerfile:1.7

# ---- 1. build the frontend --------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# ---- 2. runtime: FastAPI serves the API, the WebSockets and the built SPA ---------
FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY --from=web /web/dist ./static

# Drop root: a compromised process can't touch the OS or other users' files.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin snazzlebop \
    && chown -R snazzlebop:snazzlebop /app
USER 10001

ENV STATIC_DIR=/app/static PORT=10000
EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/healthz'%os.environ.get('PORT','10000'),timeout=2)"

# One worker on purpose: live room state is in memory (see docs/SECURITY.md and README "Scaling").
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT} --workers 1 --no-server-header --no-access-log --no-proxy-headers --ws-max-size 16384 --timeout-keep-alive 5 --limit-concurrency 400"]

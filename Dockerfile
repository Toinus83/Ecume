FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV VITE_API_URL=/api
RUN npm run build

FROM python:3.13-slim-bookworm AS wheels
WORKDIR /build
COPY backend/requirements.txt ./
RUN python -m pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ECUME_DATA_DIR=/data \
    ECUME_ENV_PATH=/data/settings.env \
    ECUME_FRONTEND_DIR=/app/frontend/dist
WORKDIR /app
COPY --from=wheels /wheels /wheels
COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels -r /tmp/requirements.txt \
    && rm -rf /wheels /tmp/requirements.txt \
    && groupadd --gid 10001 ecume \
    && useradd --uid 10001 --gid ecume --no-create-home ecume \
    && mkdir /data && chown ecume:ecume /data
COPY backend/app/ /app/backend/app/
COPY --from=frontend /build/frontend/dist/ /app/frontend/dist/
USER 10001:10001
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3).close()"]
CMD ["python", "-m", "uvicorn", "app.web:create_app", "--factory", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

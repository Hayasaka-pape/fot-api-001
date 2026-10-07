# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
# The lockfile is authoritative; npm install could resolve a different build on another PC.
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Node belongs only to the build stage; the runtime serves the resulting static files.
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST=/app/frontend/dist \
    DATA_DIR=/app/data \
    TIMEZONE=Asia/Tokyo \
    FOTMOB_TIMEOUT=10
WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 studio \
    && mkdir -p /app/data \
    && chown -R studio:studio /app/data
COPY --chown=studio:studio backend/ ./
COPY --from=frontend-build --chown=studio:studio /build/frontend/dist /app/frontend/dist
# Image users may not have the source checkout, so retain its license notices here too.
COPY LICENSE THIRD_PARTY_NOTICES.md /app/
USER studio
EXPOSE 8000
# FotMob availability does not determine app health: offline demo use must still start.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

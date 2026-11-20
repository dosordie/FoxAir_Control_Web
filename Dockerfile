# FoxAir Control Web: self-contained frontend + FastAPI backend.
# The pinned Cloud catalog must be exported before building (see docs/INSTALLATION_DOCKER.md).
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN test -s public/cloud_catalog.json && npm run build

FROM python:3.12-slim-bookworm AS base
ARG FOXAIR_SOURCE_SHA
ARG FOXAIR_VERSION
LABEL org.opencontainers.image.source="https://github.com/dosordie/FoxAir_Control_Web" \
      org.opencontainers.image.revision="$FOXAIR_SOURCE_SHA" \
      org.opencontainers.image.version="$FOXAIR_VERSION"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FOXAIR_STATE_DIR=/var/lib/foxair-web \
    FOXAIR_CONTAINER=1
WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && groupadd --gid 10001 foxair \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin foxair \
    && mkdir -p /var/lib/foxair-web \
    && chown foxair:foxair /var/lib/foxair-web \
    && chmod 0700 /var/lib/foxair-web
COPY backend/ ./backend/
COPY data/ ./data/
COPY docker/setup_admin.py ./docker/setup_admin.py
COPY VERSION ./VERSION
RUN test "$FOXAIR_VERSION" = "$(cat VERSION)"
COPY scripts/build_manifest.py ./scripts/build_manifest.py
USER 10001:10001
EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/api/health', timeout=3).close()"
CMD ["python", "-m", "backend.server", "--host", "0.0.0.0", "--port", "8081"]

FROM base AS runtime
ARG FOXAIR_SOURCE_SHA
ARG FOXAIR_BUILD_CHANNEL=work
COPY --from=frontend-build /build/frontend/dist/ ./frontend/dist/
USER root
RUN python scripts/build_manifest.py --source "$FOXAIR_SOURCE_SHA" --channel "$FOXAIR_BUILD_CHANNEL"
USER 10001:10001

FROM base AS runtime-prebuilt
ARG FOXAIR_SOURCE_SHA
COPY frontend/dist/ ./frontend/dist/
COPY build-manifest.json ./build-manifest.json
RUN python -c "import os; from backend.build_info import info; d=info(); assert d['build_consistent'] and d['source_commit']==os.environ.get('FOXAIR_SOURCE_SHA')"

FROM runtime AS final

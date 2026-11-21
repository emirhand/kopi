# syntax=docker/dockerfile:1
# Multi-stage Containerfile for Kopi (aarch64 & x86_64)

ARG NODE_IMAGE=docker.io/library/node:22.23.4-trixie-slim
ARG PYTHON_IMAGE=docker.io/library/python:3.14.4-slim-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.6

# ---------------------------------------------------------------------------
# Stage 1: Build the React/Vite kiosk SPA
# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Pinned uv binary & Python virtual environment
# ---------------------------------------------------------------------------
FROM ${UV_IMAGE} AS uv-bin

FROM ${PYTHON_IMAGE} AS python-build

COPY --from=uv-bin /uv /uvx /usr/local/bin/

ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN uv sync --frozen --no-dev --no-editable

# ---------------------------------------------------------------------------
# Stage 3: Minimal runtime image
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

ARG WITH_OCR=0
ARG EXTRA_APT_PACKAGES=""
ARG KOPI_VERSION="0.1.0"
ARG VCS_REF="unknown"

LABEL org.opencontainers.image.title="Kopi — Linux Smart Copier Appliance" \
      org.opencontainers.image.description="Headless Linux print, scan, and copy kiosk station with paired tablet UI" \
      org.opencontainers.image.source="https://github.com/placeholder/kopi" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${KOPI_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}"

RUN set -eux; \
    export DEBIAN_FRONTEND=noninteractive; \
    apt-get update; \
    ocr_pkg=""; \
    if [ "${WITH_OCR}" = "1" ]; then \
        ocr_pkg="ocrmypdf"; \
    fi; \
    # shellcheck disable=SC2086
    apt-get install -y --no-install-recommends \
        ca-certificates \
        cups-client \
        sane-airscan \
        sane-utils \
        util-linux \
        ${ocr_pkg} \
        ${EXTRA_APT_PACKAGES}; \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 kopi \
    && useradd --uid 10001 --gid 10001 --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin kopi \
    && mkdir -p /app /data/archive \
    && chown -R 10001:10001 /data \
    && chmod 0750 /data /data/archive

WORKDIR /app

COPY --from=python-build --chown=0:0 /app/.venv /app/.venv
COPY --from=frontend-build --chown=0:0 /build/frontend/dist /app/frontend/dist

ENV PATH="/app/.venv/bin:${PATH}" \
    SETTINGS_PATH="/data/settings.json" \
    KOPI_ARCHIVE_DIR="/data/archive" \
    KOPI_FRONTEND_DIST="/app/frontend/dist" \
    PORT="8000" \
    KOPI_RELOAD="0" \
    PYTHONUNBUFFERED="1" \
    PYTHONDONTWRITEBYTECODE="1"

VOLUME ["/data"]
EXPOSE 8000
USER 10001:10001

ENTRYPOINT ["kopi"]
CMD ["serve"]

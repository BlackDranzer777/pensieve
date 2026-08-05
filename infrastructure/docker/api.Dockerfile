# syntax=docker/dockerfile:1
#
# FastAPI backend.
#
# Multi-stage: dependencies are resolved into a wheel-free virtualenv in the
# builder, then only the built virtualenv and the source are copied into a slim
# runtime image. That keeps compilers and build caches out of the final layer.

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only what the dependency resolution needs first, so the (slow) install
# layer is cached until the dependency list itself changes.
COPY pyproject.toml README.md ./
COPY pipelines/__init__.py ./pipelines/
COPY apps/api/app/__init__.py ./apps/api/app/

# `serving`, not `pipelines`: the API reads Parquet but never runs language
# detection or model training, so Lingua, SciPy and scikit-learn are excluded.
RUN pip install --upgrade pip && \
    pip install ".[api,serving]"

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# curl is used by the compose healthcheck.
RUN apt-get update && \
    apt-get install --no-install-recommends -y curl && \
    rm -rf /var/lib/apt/lists/*

# Run as a non-root user: a container that never needs to write outside its
# data volume has no reason to run as root.
RUN useradd --create-home --uid 1001 pensieve

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=pensieve:pensieve pyproject.toml README.md ./
COPY --chown=pensieve:pensieve pipelines ./pipelines
COPY --chown=pensieve:pensieve apps/api ./apps/api

# Install the project itself (not its dependencies) so `app` and `pipelines`
# are importable as packages.
RUN pip install --no-deps --no-cache-dir -e . && \
    chown -R pensieve:pensieve /app

USER pensieve

EXPOSE 8000

# 127.0.0.1 rather than `localhost` for the same reason as the web image: the
# name also resolves to ::1, and uvicorn binds IPv4 here.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl --fail --silent http://127.0.0.1:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

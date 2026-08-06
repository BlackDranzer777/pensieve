# syntax=docker/dockerfile:1
#
# PySpark job runner for the Silver -> Gold stage.
#
# Why this exists: PySpark 4.x requires Java 17+. Debian trixie ships JDK 21
# (17 was dropped), and Spark 4 supports both, so 21 is the right choice here., and Spark on Windows also
# wants a Hadoop `winutils.exe` before it will write Parquet locally. Shipping
# the JDK in a container removes both problems and makes the Gold stage
# reproducible on any host, regardless of the JDK installed there.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    PATH="/opt/venv/bin:/usr/lib/jvm/java-21-openjdk-amd64/bin:$PATH"

RUN apt-get update && \
    apt-get install --no-install-recommends -y openjdk-21-jre-headless procps && \
    rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv

WORKDIR /app

COPY pyproject.toml README.md ./
COPY pipelines/__init__.py ./pipelines/
COPY apps/api/app/__init__.py ./apps/api/app/

RUN pip install --upgrade pip && \
    pip install --no-cache-dir ".[pipelines,spark]"

COPY pipelines ./pipelines
# The Gold queries live here and are read at runtime by both engines.
COPY analytics ./analytics
COPY apps/api ./apps/api
RUN pip install --no-deps --no-cache-dir -e .

# Overridden by `docker compose run` when a specific job is requested.
CMD ["python", "-m", "pipelines.jobs.run_gold", "--engine", "spark"]

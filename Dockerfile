# syntax=docker/dockerfile:1
FROM python:3.12-slim@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54 AS runtime

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN groupadd --system gafam && useradd --system --gid gafam --create-home gafam

COPY pyproject.toml README.md Dockerfile ./
COPY docker-compose.yml docker-compose.ci.yml .yamllint.yml .hadolint.yaml ./
COPY src ./src
COPY data ./data
COPY schema ./schema
COPY tests ./tests
COPY scripts ./scripts
COPY .github ./.github

# hadolint ignore=DL3013
RUN pip install --upgrade pip \
    && pip install . \
    && chown -R gafam:gafam /app

USER gafam
CMD ["python", "-m", "gafam_contratos"]

FROM runtime AS ci

USER root
# hadolint ignore=DL3008,DL3013
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates tar \
    && curl -sSfL \
      https://github.com/rhysd/actionlint/releases/download/v1.7.7/actionlint_1.7.7_linux_amd64.tar.gz \
      | tar -xz -C /usr/local/bin actionlint \
    && curl -sSfL \
      https://github.com/hadolint/hadolint/releases/download/v2.12.0/hadolint-Linux-x86_64 \
      -o /usr/local/bin/hadolint \
    && chmod +x /usr/local/bin/hadolint /usr/local/bin/actionlint \
    && pip install '.[dev]' yamllint pip-audit \
    && pip-audit \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

USER gafam
CMD ["bash", "scripts/quality.sh"]

# syntax=docker/dockerfile:1.7
ARG OPENCLAW_BASE_IMAGE="ghcr.io/openclaw/openclaw:2026.4.19-beta.2-slim@sha256:806e0945352eb232a847dc944339d0a2d0be06084ada945e11471d24ea428086"
FROM ${OPENCLAW_BASE_IMAGE}

USER root

ARG HOMEBREW_VERSION=5.1.6
ENV HOMEBREW_PREFIX=/home/linuxbrew/.linuxbrew \
    HOMEBREW_CELLAR=/home/linuxbrew/.linuxbrew/Cellar \
    HOMEBREW_REPOSITORY=/home/linuxbrew/.linuxbrew/Homebrew

# OpenClaw slim already includes curl, git, and procps. Homebrew on Debian
# still needs certificates, build tools, and the `file` utility to bootstrap.
RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        file; \
    rm -rf /var/lib/apt/lists/*; \
    install -d -m 0755 "${HOMEBREW_REPOSITORY}"; \
    git clone --branch "${HOMEBREW_VERSION}" --depth 1 https://github.com/Homebrew/brew "${HOMEBREW_REPOSITORY}"; \
    install -d -m 0755 \
        "${HOMEBREW_PREFIX}/bin" \
        "${HOMEBREW_PREFIX}/etc" \
        "${HOMEBREW_PREFIX}/include" \
        "${HOMEBREW_PREFIX}/lib" \
        "${HOMEBREW_PREFIX}/opt" \
        "${HOMEBREW_PREFIX}/sbin" \
        "${HOMEBREW_PREFIX}/share" \
        "${HOMEBREW_PREFIX}/var" \
        "${HOMEBREW_CELLAR}" \
        /home/linuxbrew/.cache/Homebrew \
        /usr/share/openquad/defaults; \
    ln -s "${HOMEBREW_REPOSITORY}/bin/brew" "${HOMEBREW_PREFIX}/bin/brew"; \
    chown -R node:node /home/linuxbrew

COPY files/profile.d/linuxbrew.sh /etc/profile.d/linuxbrew.sh
COPY defaults/openclaw.base.json5 /usr/share/openquad/defaults/openclaw.base.json5

ENV PATH="${HOMEBREW_PREFIX}/bin:${HOMEBREW_PREFIX}/sbin:${PATH}"

USER node
WORKDIR /app

RUN set -eux; \
    brew --version

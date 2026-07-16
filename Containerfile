# syntax=docker/dockerfile:1.7
ARG OPENCLAW_BASE_IMAGE="ghcr.io/openclaw/openclaw:slim"
FROM ${OPENCLAW_BASE_IMAGE}

USER root

ARG HOMEBREW_VERSION=5.1.6
ENV HOMEBREW_PREFIX=/home/linuxbrew/.linuxbrew \
    HOMEBREW_CELLAR=/home/linuxbrew/.linuxbrew/Cellar \
    HOMEBREW_REPOSITORY=/home/linuxbrew/.linuxbrew/Homebrew \
    HOMEBREW_NO_ANALYTICS=1 \
    HOMEBREW_NO_AUTO_UPDATE=1 \
    HOMEBREW_NO_ENV_HINTS=1

ENV GROTTO_RUNTIME=openclaw \
    GROTTO_UPDATE_MODE=image \
    HOME=/config \
    OPENCLAW_HOME=/config \
    OPENCLAW_STATE_DIR=/config/.openclaw \
    OPENCLAW_CONFIG_DIR=/config/.openclaw \
    OPENCLAW_CONFIG_PATH=/config/.openclaw/openclaw.json \
    OPENCLAW_WORKSPACE_DIR=/workspace \
    XDG_CONFIG_HOME=/config/.config \
    XDG_DATA_HOME=/config/.local/share \
    XDG_STATE_HOME=/config/.local/state \
    XDG_CACHE_HOME=/cache/xdg \
    CODEX_HOME=/config/.codex \
    NPM_CONFIG_PREFIX=/tools/npm \
    NPM_CONFIG_CACHE=/cache/npm \
    PNPM_HOME=/tools/pnpm \
    BUN_INSTALL=/tools/bun \
    UV_TOOL_DIR=/tools/uv/tools \
    UV_TOOL_BIN_DIR=/tools/bin \
    UV_CACHE_DIR=/cache/uv \
    PIPX_HOME=/tools/pipx \
    PIPX_BIN_DIR=/tools/bin \
    PIP_CACHE_DIR=/cache/pip \
    MISE_DATA_DIR=/tools/mise \
    MISE_CACHE_DIR=/cache/mise \
    MISE_CONFIG_DIR=/config/mise \
    CARGO_HOME=/tools/cargo \
    GOBIN=/tools/bin \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        file \
        python3 \
        python3-pip \
        python3-venv \
        unzip \
        xz-utils \
        zstd; \
    rm -rf /var/lib/apt/lists/*; \
    install -d -m 0755 \
        "${HOMEBREW_REPOSITORY}" \
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
        /usr/share/grotto; \
    git clone --branch "${HOMEBREW_VERSION}" --depth 1 \
        https://github.com/Homebrew/brew "${HOMEBREW_REPOSITORY}"; \
    ln -s "${HOMEBREW_REPOSITORY}/bin/brew" "${HOMEBREW_PREFIX}/bin/brew"; \
    install -d -o node -g node -m 0755 \
        /config \
        /workspace \
        /tools \
        /cache \
        /tools/apps \
        /tools/bin \
        /tools/npm \
        /tools/pnpm \
        /tools/bun \
        /tools/cargo \
        /tools/mise \
        /cache/homebrew \
        /cache/mise \
        /cache/npm \
        /cache/pip \
        /cache/uv \
        /cache/xdg; \
    chown -R node:node /home/linuxbrew

COPY Brewfile /usr/share/grotto/Brewfile
COPY files/grotto-openclaw-entrypoint /usr/local/bin/grotto-openclaw-entrypoint
COPY files/profile.d/linuxbrew.sh /etc/profile.d/linuxbrew.sh

ENV HOMEBREW_CACHE=/cache/homebrew \
    PATH=/tools/bin:/tools/npm/bin:/tools/pnpm:/tools/bun/bin:/tools/cargo/bin:/tools/mise/shims:/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

USER node
WORKDIR /workspace

RUN set -eux; \
    brew --version; \
    HOMEBREW_NO_AUTO_UPDATE=0 brew update --force --quiet; \
    brew bundle --file=/usr/share/grotto/Brewfile; \
    command -v jq; \
    command -v yq; \
    command -v rg; \
    command -v uv; \
    command -v mise; \
    command -v openclaw; \
    brew cleanup --prune=all -s || true; \
    rm -rf "$(brew --cache)" /home/linuxbrew/.cache/Homebrew 2>/dev/null || true

USER root
RUN chmod 0755 /usr/local/bin/grotto-openclaw-entrypoint; \
    sh -n /usr/local/bin/grotto-openclaw-entrypoint; \
    chown -R node:node /config /workspace /tools /cache

VOLUME ["/config", "/workspace", "/tools", "/cache"]
EXPOSE 18789

USER node
ENTRYPOINT ["tini", "-s", "--", "/usr/local/bin/grotto-openclaw-entrypoint"]
CMD ["openclaw", "gateway", "--bind", "lan", "--port", "18789"]

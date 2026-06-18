# syntax=docker/dockerfile:1.7
ARG OPENCLAW_BASE_IMAGE="ghcr.io/openclaw/openclaw:slim"
FROM ${OPENCLAW_BASE_IMAGE}

ARG OPENQUAD_TEMPLATE="communications-calendar"
ARG OPENQUAD_IMAGE_NAME="openquad-comms"
ARG OPENQUAD_LINK_FORMULAE=""
ARG OPENQUAD_NPM_PACKAGES=""
ARG OPENQUAD_VERIFY_TOOLS=""

USER root

ARG HOMEBREW_VERSION=5.1.6
ENV HOMEBREW_PREFIX=/home/linuxbrew/.linuxbrew \
    HOMEBREW_CELLAR=/home/linuxbrew/.linuxbrew/Cellar \
    HOMEBREW_REPOSITORY=/home/linuxbrew/.linuxbrew/Homebrew \
    HOMEBREW_NO_ANALYTICS=1 \
    HOMEBREW_NO_AUTO_UPDATE=1 \
    HOMEBREW_NO_ENV_HINTS=1

ENV OPENQUAD_TEMPLATE=${OPENQUAD_TEMPLATE} \
    OPENQUAD_IMAGE_NAME=${OPENQUAD_IMAGE_NAME} \
    OPENCLAW_STATE_DIR=/home/node/.openclaw \
    OPENCLAW_CONFIG_PATH=/home/node/.openclaw/openclaw.json \
    OPENQUAD_DEFAULT_CONFIG=/usr/share/openquad/templates/${OPENQUAD_TEMPLATE}/openclaw.json5 \
    NPM_CONFIG_CACHE=/home/node/.openclaw/.npm \
    NPM_CONFIG_PREFIX=/home/node/.local \
    XDG_CONFIG_HOME=/home/node/.openclaw/.config \
    XDG_DATA_HOME=/home/node/.openclaw/.local/share \
    XDG_CACHE_HOME=/home/node/.openclaw/.cache \
    CODEX_HOME=/home/node/.openclaw/.codex \
    CODEX_SQLITE_HOME=/home/node/.openclaw/.codex/sqlite \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    OPENQUAD_WORKERD_ENABLED=true \
    OPENQUAD_WORKERD_HOST=0.0.0.0 \
    OPENQUAD_WORKERD_PORT=18789 \
    OPENQUAD_WORKSPACE_DIR=/home/node/.openclaw/workspace \
    OPENQUAD_MANIFEST_PATH=/usr/share/openquad/templates/${OPENQUAD_TEMPLATE}/openquad.manifest.json

# OpenClaw slim already includes curl, git, and procps. Homebrew on Debian
# still needs certificates, build tools, and the `file` utility to bootstrap.
RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        file \
        python3 \
        python3-venv; \
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
        /usr/share/openquad/templates/${OPENQUAD_TEMPLATE}; \
    install -d -o node -g node -m 0755 \
        /home/node/.cache \
        /home/node/.local \
        /home/node/.npm \
        /home/node/.openclaw \
        /home/node/.openclaw/.cache \
        /home/node/.openclaw/.codex \
        /home/node/.openclaw/.codex/sqlite \
        /home/node/.openclaw/.config \
        /home/node/.openclaw/.local/share \
        /home/node/.openclaw/.npm \
        /home/node/.openclaw/workspace \
        /usr/share/openquad/schemas \
        /opt/openquad/workerd; \
    ln -s "${HOMEBREW_REPOSITORY}/bin/brew" "${HOMEBREW_PREFIX}/bin/brew"; \
    chown -R node:node /home/linuxbrew /home/node/.local

COPY files/profile.d/linuxbrew.sh /etc/profile.d/linuxbrew.sh
COPY defaults/openclaw.base.json5 /usr/share/openquad/defaults/openclaw.base.json5
COPY schemas /usr/share/openquad/schemas
COPY workerd /opt/openquad/workerd
COPY templates/${OPENQUAD_TEMPLATE}/Brewfile /usr/share/openquad/templates/${OPENQUAD_TEMPLATE}/Brewfile
COPY templates/${OPENQUAD_TEMPLATE}/openclaw.json5 /usr/share/openquad/templates/${OPENQUAD_TEMPLATE}/openclaw.json5
COPY templates/${OPENQUAD_TEMPLATE}/openquad.manifest.json /usr/share/openquad/templates/${OPENQUAD_TEMPLATE}/openquad.manifest.json

RUN set -eux; \
    python3 -m venv /opt/openquad/workerd/.venv; \
    /opt/openquad/workerd/.venv/bin/pip install --no-cache-dir /opt/openquad/workerd; \
    ln -sf /opt/openquad/workerd/.venv/bin/openquad-workerd /usr/local/bin/openquad-workerd; \
    test -r /usr/share/openquad/schemas/openquad-task.schema.json; \
    test -r "/usr/share/openquad/templates/${OPENQUAD_TEMPLATE}/openquad.manifest.json"

ENV PATH="/home/node/.local/bin:${HOMEBREW_PREFIX}/bin:${HOMEBREW_PREFIX}/sbin:${PATH}"

USER node
WORKDIR /home/node

RUN set -eux; \
    brew --version; \
    HOMEBREW_NO_AUTO_UPDATE=0 brew update --force --quiet; \
    brew bundle --file="/usr/share/openquad/templates/${OPENQUAD_TEMPLATE}/Brewfile"; \
    if [ -n "${OPENQUAD_LINK_FORMULAE}" ]; then \
        for formula in ${OPENQUAD_LINK_FORMULAE}; do brew link --force --overwrite "${formula}"; done; \
    fi; \
    if [ -n "${OPENQUAD_NPM_PACKAGES}" ]; then \
        npm install --global ${OPENQUAD_NPM_PACKAGES}; \
    fi; \
    for tool in ${OPENQUAD_VERIFY_TOOLS}; do \
        command -v "${tool}"; \
    done; \
    test -r /usr/share/openquad/defaults/openclaw.base.json5; \
    test -r "/usr/share/openquad/templates/${OPENQUAD_TEMPLATE}/Brewfile"; \
    test -r "/usr/share/openquad/templates/${OPENQUAD_TEMPLATE}/openclaw.json5"; \
    brew cleanup --prune=all -s || true; \
    rm -rf "$(brew --cache)" /home/linuxbrew/.cache/Homebrew "${NPM_CONFIG_CACHE}"/_cacache 2>/dev/null || true

EXPOSE 18789

CMD ["sh", "-lc", "if [ \"${OPENQUAD_WORKERD_ENABLED:-true}\" = \"true\" ]; then exec openquad-workerd; else exec sleep infinity; fi"]

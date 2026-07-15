# Grotto ChatGPT Desktop

`grotto-chatgpt-desktop` is a single-application interactive runtime that
streams the unofficial Linux build of ChatGPT Desktop through LinuxServer's
Selkies base image.

It is not a Grotto worker-contract image. It does not expose `grotto-workerd`
or accept orchestrator tasks. It is intended as an interactive Codex workbench
that can share a mounted project workspace with other Pelagian development
tools.

## Image construction

The application is built entirely at image build time:

1. Clone a pinned revision of
   [`ilysenko/codex-desktop-linux`](https://github.com/ilysenko/codex-desktop-linux).
2. Download the official upstream ChatGPT macOS DMG.
3. Extract and patch the Electron application for Linux.
4. Run the wrapper's candidate and acceptance checks.
5. Rebuild native modules.
6. Install `@openai/codex` with its Linux optional dependency.
7. Copy only the completed application and CLI into the Selkies runtime stage.

Container startup does not download the DMG, run npm, or compile native code.

## CI behavior

The image is part of the main
[`.github/workflows/build.yml`](../.github/workflows/build.yml) matrix alongside
the other Grotto images.

It builds on:

- pull requests targeting `main`
- pushes to `main`
- version tags
- scheduled rebuilds
- manual workflow dispatch

Pull-request builds validate the image without publishing it. All other events
use the same GHCR login, metadata, tags, and publication rule as the other
Grotto images. A successful `main` build publishes:

```text
ghcr.io/pelagians/grotto-chatgpt-desktop:latest
```

The desktop matrix entry reclaims unused GitHub-hosted runner toolchains before
building because the DMG and expanded Electron application require substantial
temporary storage. That cleanup is conditional and does not run for the smaller
agent images.

The wrapper is open source, while the upstream ChatGPT Desktop payload retains
its own license and distribution terms.

## Local build

The image is large. Keep at least 15 GiB free in the container engine's graph
store.

```bash
podman build \
  --file Containerfile.chatgpt-desktop \
  --tag localhost/grotto-chatgpt-desktop:dev \
  .
```

Override the pinned wrapper revision or Codex CLI version:

```bash
podman build \
  --file Containerfile.chatgpt-desktop \
  --build-arg CODEX_DESKTOP_LINUX_REF=52e9701e3f1be291821cff904b6cd4bdce30998d \
  --build-arg CODEX_CLI_VERSION=latest \
  --tag localhost/grotto-chatgpt-desktop:dev \
  .
```

## Run with Intel or AMD graphics

```bash
mkdir -p chatgpt-config workspace

podman run --rm \
  --name grotto-chatgpt-desktop \
  --shm-size=2g \
  --device /dev/dri:/dev/dri \
  --group-add keep-groups \
  --publish 3001:3001 \
  --env PUID="$(id -u)" \
  --env PGID="$(id -g)" \
  --env TZ=America/Vancouver \
  --env CUSTOM_USER=abc \
  --env PASSWORD=change-me \
  --env PIXELFLUX_WAYLAND=true \
  --env AUTO_GPU=true \
  --volume "$PWD/chatgpt-config:/config:Z" \
  --volume "$PWD/workspace:/workspace:Z" \
  ghcr.io/pelagians/grotto-chatgpt-desktop:latest
```

Open `https://localhost:3001`. Selkies uses a self-signed certificate unless a
reverse proxy terminates TLS.

For a CPU/X11 fallback, omit `/dev/dri` and use:

```bash
--env PIXELFLUX_WAYLAND=false \
--env AUTO_GPU=false \
--env CODEX_OZONE_PLATFORM=x11
```

## Persistent state

- `/config/.config` contains application configuration.
- `/config/.cache` contains application logs and cache.
- `/config/.local/state` contains launcher state.
- `/config/.codex` contains Codex credentials and project state.
- `/workspace` is the project workspace.

Treat `/config` as sensitive. It can contain authenticated application and
Codex state.

## Runtime boundaries

The image provides:

- ChatGPT Desktop UI
- Codex CLI
- Selkies HTTPS desktop streaming
- persistent application state
- a mounted project workspace

The image does not provide:

- Grotto worker-contract endpoints
- Nereus workflow orchestration
- browser-worker isolation
- tenant policy or audit storage
- automatic credential provisioning

Expose Selkies only behind an authenticated private network or a proper
application gateway. LinuxServer describes its built-in basic authentication
as a convenience layer, not an internet-grade security boundary.

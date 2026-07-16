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

## First-run authentication

The image does not install a full web browser. When no readable Codex session
exists, Grotto opens a dedicated authentication window before ChatGPT Desktop.
It starts the supported Codex device-code flow with stdin disconnected, so
ordinary keyboard input cannot dismiss the window or accidentally skip sign-in.

The window provides:

- a scannable QR code for the OpenAI device page
- an `Open sign-in page` action that also falls back to copying the URL
- explicit `Copy link` and `Copy code` buttons
- a selectable URL and one-time code
- a 15-minute expiration countdown
- explicit retry and confirmed skip actions
- clear DNS and timeout errors

Complete authentication in the normal host browser or on another device. The
dialog closes only after Codex confirms the session, then ChatGPT Desktop starts
using the same persisted state.

The bootstrap runs as LinuxServer's `abc` account. Its credentials are written
to `/config/.codex/auth.json` with restrictive permissions and are readable by
the desktop app. A custom container-init script repairs ownership on existing
state before the graphical session starts, including state accidentally created
by a prior root-level `podman exec` login.

Disable the first-run bootstrap when authentication is managed externally:

```bash
--env GROTTO_CHATGPT_AUTH_MODE=off
```

For a manual login, always run the CLI as the desktop user:

```bash
podman exec \
  --user abc \
  --env HOME=/config \
  --env CODEX_HOME=/config/.codex \
  -it grotto-chatgpt-desktop \
  /opt/codex-cli/bin/codex login --device-auth
```

Verify the session from the same account:

```bash
podman exec \
  --user abc \
  --env HOME=/config \
  --env CODEX_HOME=/config/.codex \
  grotto-chatgpt-desktop \
  /opt/codex-cli/bin/codex login status
```

### Rootless Podman DNS

Some Fedora rootless Podman setups inherit link-local or Tailscale resolvers
that are not reachable from the container. The symptom is a device-auth request
that hangs or reports `error sending request` while host networking works.

Recreate the container with explicit resolvers when this occurs:

```bash
--dns=1.1.1.1 \
--dns=8.8.8.8
```

Production and enterprise deployments should use organization-approved DNS
servers instead of hard-coded public resolvers.

## Persistent state

- `/config/.config` contains application configuration.
- `/config/.cache` contains application logs and cache.
- `/config/.local/state` contains launcher state.
- `/config/.codex` contains Codex credentials and project state.
- `/workspace` is the project workspace.

Treat `/config` as sensitive. It can contain authenticated application and
Codex state.

## Remove the local runtime completely

The following removes only the Grotto ChatGPT Desktop test container, pulled
image, and persisted state. It does not prune unrelated Podman images or
containers.

```bash
STATE="$HOME/.local/share/grotto/chatgpt-desktop"

podman rm --force grotto-chatgpt-desktop 2>/dev/null || true
podman image rm --force \
  ghcr.io/pelagians/grotto-chatgpt-desktop:latest \
  2>/dev/null || true
rm -rf -- "$STATE"

podman ps -a --filter name=grotto-chatgpt-desktop
podman images ghcr.io/pelagians/grotto-chatgpt-desktop
```

When the runtime was launched from another bind-mount location, remove that
specific configuration and workspace directory separately.

## Runtime boundaries

The image provides:

- ChatGPT Desktop UI
- Codex CLI
- browserless graphical device-code authentication
- Selkies HTTPS desktop streaming
- persistent application state
- a mounted project workspace

The image does not provide:

- Grotto worker-contract endpoints
- Nereus workflow orchestration
- browser-worker isolation
- tenant policy or audit storage
- a full browser session inside the container
- external credential injection or organization SSO brokering

Expose Selkies only behind an authenticated private network or a proper
application gateway. LinuxServer describes its built-in basic authentication
as a convenience layer, not an internet-grade security boundary.

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

Pull-request builds load the completed desktop image and run
`grotto-chatgpt-desktop-smoke` as the effective `abc` desktop user. The smoke
test runs `/bin/true`, validates the stable `grotto-doctor --json` schema, checks
the persistent roots, and records Bubblewrap and Landlock results. GitHub's
Docker runner does not validate Fedora SELinux or rootless Podman behavior; use
the separate Fedora procedure below for that boundary.

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
  --build-arg CODEX_CLI_VERSION=0.144.5 \
  --tag localhost/grotto-chatgpt-desktop:dev \
  .
```

Component updates are intentional and reviewable:

1. Check the current Codex release with `npm view @openai/codex version` and
   update both the Containerfile default and CI matrix value.
2. Resolve the Selkies index digest with
   `docker buildx imagetools inspect ghcr.io/linuxserver/baseimage-selkies:debiantrixie`.
3. When changing 7-Zip, update the architecture-specific checksums from the
   publisher and verify every supported archive.
4. Build the image, run `grotto-doctor --json`, and review the recorded wrapper,
   Codex, base-image, desktop, Electron, and DMG metadata.

Published builds attach SBOM and provenance attestations. Pull-request image
loads disable attestations because the local Docker image exporter does not
retain registry attestations.

## Run with Intel or AMD graphics

```bash
mkdir -p chatgpt-config workspace tools cache

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
  --volume "$PWD/tools:/tools:Z" \
  --volume "$PWD/cache:/cache:Z" \
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
- `/tools` contains persistent user-installed tools and language environments.
- `/cache` contains disposable npm, pip, and uv package caches.

Treat `/config` as sensitive. It can contain authenticated application and
Codex state.

## Workbench tools and persistent paths

Live inventory confirmed that Selkies already supplies the compiler, shell,
Git, curl, jq, Python, and standard system utilities. The desktop image adds
only the missing baseline tools: `gh`, `lsof`, `pkg-config`, `pip3`,
`ripgrep`, `shellcheck`, `sqlite3`, `unzip`, and `zip`.

Persistent installation paths are configured as follows:

| Purpose | Path |
| --- | --- |
| General executables | `/tools/bin` |
| npm global prefix | `/tools/npm` |
| pnpm home | `/tools/pnpm` |
| Cargo home | `/tools/cargo` |
| mise data and shims | `/tools/mise` |
| Python user base and virtual environments | `/tools/python` and `/tools/venvs` |
| pipx state | `/tools/pipx` |
| npm, pip, and uv caches | `/cache/npm`, `/cache/pip`, and `/cache/uv` |

The init script creates only Grotto-managed directories, assigns them to
`abc`, and does not recursively change project ownership. The graphical
terminal can install tools into these locations. Codex sandbox commands receive
the active permission profile: `/tools` remains read/execute unless a profile
explicitly grants a tool-installation task write access. Grotto does not make
`/tools` writable in every sandbox.

## Runtime diagnostics

Run the non-destructive doctor inside the image:

```bash
podman exec \
  --user abc \
  --env HOME=/config \
  --env CODEX_HOME=/config/.codex \
  grotto-chatgpt-desktop \
  grotto-doctor

podman exec \
  --user abc \
  --env HOME=/config \
  --env CODEX_HOME=/config/.codex \
  grotto-chatgpt-desktop \
  grotto-doctor --json
```

The JSON schema reports component versions, identity and groups, environment
paths, mount and device state, SELinux and seccomp status, user namespaces,
direct execution, Bubblewrap primitives, Codex permission profiles, Landlock
diagnostics, and OpenAI authentication-host DNS and HTTPS connectivity.

The current rootless Fedora container has an unresolved nested Bubblewrap
limitation. Direct terminal commands work, while fresh devpts setup and
synthetic protected-path remounts fail. Grotto does not install an automatic
fallback, bind the complete outer `/dev`, or weaken `.git`, `.agents`, or
`.codex` protections. See
[ChatGPT Desktop sandbox investigation](chatgpt-desktop-sandbox.md) for exact
commands, timestamps, syscall traces, device differences, and remaining
architecture candidates.

For Fedora validation, run the image with rootless Podman, normal seccomp,
SELinux enforcing, and `:Z` volume labels. Capture host AVC records for the
doctor interval. The container normally cannot read that host audit stream;
host-side correlation for the documented reproduction confirmed SELinux
denials for filesystem remount, fresh devpts mount, occasional proc mount, and
tmpfs relabel operations. Do not infer Fedora SELinux behavior from
GitHub-hosted Docker CI.

Run the correlated query on the Fedora host, not inside the container:

~~~bash
START_DATE="$(LC_TIME=C date -d '2026-07-16' +%x)"
sudo env LC_TIME=C ausearch \
  -m AVC,USER_AVC \
  -ts "$START_DATE" 12:48:09 \
  -i
~~~

Use the output for diagnosis. Do not generate or install broad
'audit2allow' rules for the reported 'container_t' filesystem permissions.

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

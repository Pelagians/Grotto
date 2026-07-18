# Grotto Claude Desktop

`grotto-claude-desktop` packages Anthropic's official Linux beta of Claude
Desktop in LinuxServer's Selkies base image. It is an interactive workbench,
not a Grotto worker-contract image, and does not expose workflow orchestration
or tenant policy APIs.

The image provides Claude Chat, the Claude Code desktop interface available to
eligible plans, a mounted project workspace, persistent application state, and
the same user-managed tool and cache boundaries as the other Grotto images.

## Image construction

The image installs `claude-desktop` from Anthropic's signed stable APT
repository during the image build. It verifies the published signing-key
fingerprint before trusting the repository:

```text
31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE
```

The application does not update itself inside a running container. Pulling a
new Grotto image replaces the image-managed Claude Desktop package while
preserving mounted user state.

The installed package version is recorded at:

```text
/usr/share/grotto/claude-desktop-version
```

The first implementation tracks the current stable package candidate. A
specific version can be selected at build time with
`CLAUDE_DESKTOP_VERSION=<apt-version>`.

## Local build

```bash
podman build \
  --file Containerfile.claude-desktop \
  --tag localhost/grotto-claude-desktop:dev \
  .
```

Build a specific package version:

```bash
podman build \
  --file Containerfile.claude-desktop \
  --build-arg CLAUDE_DESKTOP_VERSION='<apt-version>' \
  --tag localhost/grotto-claude-desktop:dev \
  .
```

## Run with Intel or AMD graphics

```bash
mkdir -p claude-config workspace tools cache

podman run --rm \
  --name grotto-claude-desktop \
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
  --volume "$PWD/claude-config:/config:Z" \
  --volume "$PWD/workspace:/workspace:Z" \
  --volume "$PWD/tools:/tools:Z" \
  --volume "$PWD/cache:/cache:Z" \
  ghcr.io/pelagians/grotto-claude-desktop:latest
```

Open `https://localhost:3001`. Selkies uses a self-signed certificate unless a
reverse proxy terminates TLS.

For a CPU/X11 fallback, omit `/dev/dri` and use:

```bash
--env PIXELFLUX_WAYLAND=false \
--env AUTO_GPU=false \
--env ELECTRON_OZONE_PLATFORM_HINT=x11
```

## Authentication and secrets

Sign in through Claude Desktop's first-run interface. The image does not bake
credentials or copy Claude Code CLI tokens into the desktop application.

`Sign in with Google` requires an external browser rather than an embedded
Electron webview. The image includes Firefox ESR and registers it as the
HTTP/HTTPS browser inside the Selkies desktop. Clicking the Google button opens
a Firefox window in the same streamed session. Complete Google authentication
there, then accept the browser's request to return to Claude Desktop if it
prompts to open a `claude://` link.

The same-session browser is intentional. Opening the login URL on the Podman
host would leave the OAuth return protocol on the host, where it could not
reach Claude Desktop inside the container. Grotto registers
`x-scheme-handler/claude` to `/usr/local/bin/grotto-claude-url-handler`, which
passes the return URL to the running desktop application.

Firefox state is stored beneath `/config` because the container sets
`HOME=/config`. Treat it as sensitive alongside the Claude session. To retry
from a completely clean browser and Claude session, stop the container and
remove only the relevant test configuration directory after backing up anything
that must be retained.

Claude application state is redirected under `/config` by setting `HOME` and
the XDG paths to persistent locations. The launcher also starts the Secret
Service component of `gnome-keyring-daemon` when possible, and persists its
keyring data under `/config/.local/share/keyrings`.

Treat `/config` as sensitive. It can contain authenticated sessions, browser
cookies, Claude settings, extension credentials, MCP configuration, and Claude
Code state.

## Persistent state

| Path | Purpose | Persistence |
| --- | --- | --- |
| `/config` | Claude sessions, browser profile, settings, keyrings, and application state | Required |
| `/workspace` | Project repositories and working files | Required |
| `/tools` | User-installed tools and language environments | Recommended |
| `/cache` | Disposable package caches | Optional |

Important paths inside `/config` include:

- `/config/.claude` for Claude Code settings and state
- `/config/.claude.json` when created by Claude
- `/config/.config` for application configuration and URL-handler associations
- `/config/.cache` for application cache and logs
- `/config/.local/share/keyrings` for Secret Service state
- `/config/.mozilla` for the Firefox profile used during authentication

The container initialization script repairs ownership only for Grotto-managed
configuration, tool, and cache paths. It does not recursively rewrite the
mounted project workspace.

## Workbench tools

The image includes a practical baseline for local development and MCP servers:
Git, GitHub CLI, SSH, curl, jq, Python, pip, ripgrep, shellcheck, SQLite,
archive tools, D-Bus utilities, Secret Service support, and Firefox ESR for
account authentication.

Persistent installation paths match `grotto-chatgpt-desktop`:

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

## Claude Code and Cowork boundaries

Claude Desktop's Code tab is part of the packaged desktop application. The
separate `claude-code` CLI package is not installed in this first image.

Cowork is present only to the extent provided by the upstream application. It
is not validated or supported by the initial Grotto runtime because its Linux
execution environment requires KVM access, QEMU support, substantial memory,
and a large workspace image. The default run command does not pass `/dev/kvm`.

Anthropic currently lists computer use and dictation as unavailable in the
Linux beta. Native Wayland global shortcuts also depend on desktop portal
support and may differ from X11 behavior.

## Runtime validation

Run the non-GUI smoke test inside the image:

```bash
podman run --rm \
  --user abc \
  --env HOME=/config \
  --entrypoint /usr/local/libexec/grotto-claude-desktop-smoke \
  ghcr.io/pelagians/grotto-claude-desktop:latest
```

The smoke test verifies the package, repository signing key, recorded version,
Selkies executable, Firefox executable, Secret Service dependency, writable
persistent roots, HTTP/HTTPS browser association, and `claude://` return
handler. It intentionally does not launch the graphical client or authenticate.

The remaining integration checks require an actual Selkies session:

1. Claude renders in Wayland/Labwc and X11/Openbox modes.
2. `Sign in with Google` opens Firefox inside Selkies and returns to Claude.
3. Authentication survives replacement of the container.
4. File and folder selection can access `/workspace`.
5. Claude Code can edit a mounted repository and invoke installed tools.
6. Secret Service state survives restart without plaintext fallback flags.
7. The runtime works under rootless Podman without disabling SELinux or seccomp.

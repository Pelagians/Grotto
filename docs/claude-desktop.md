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

## Host browser bridge

Claude Desktop delegates Google authentication to the operating system's
browser. Grotto keeps the browser on the Podman host rather than adding a
second browser and browser profile to the image.

Install the user-scoped bridge from the repository:

```bash
python3 contrib/claude-host-bridge/grotto-claude-host-bridge install
```

The installer performs four user-level actions:

1. Copies the bridge to `~/.local/bin/grotto-claude-host-bridge`.
2. Starts `grotto-claude-host-bridge.service` through the systemd user manager.
3. Registers the host's `claude://` handler.
4. Creates the shared bridge directory inside the private user runtime root.

Check its state with:

```bash
~/.local/bin/grotto-claude-host-bridge status
```

A healthy host service reports `Host browser socket: ready`. The Claude
callback socket remains `missing` until the container and its graphical session
are running.

On systems without a usable systemd user manager, start the service from the
host graphical session before clicking the sign-in button:

```bash
~/.local/bin/grotto-claude-host-bridge serve
```

The bridge uses a shared Unix-socket directory rather than TCP ports:

```text
Claude Desktop
  -> /run/grotto/claude-bridge/host.sock
  -> host xdg-open
  -> normal host browser
  -> host claude:// handler
  -> /run/grotto/claude-bridge/claude.sock
  -> running Claude Desktop session
```

The host endpoint accepts only absolute `https://` URLs. The container endpoint
accepts only `claude://` callbacks. The parent `$XDG_RUNTIME_DIR` remains private
to the logged-in host user. The mounted child directory and sockets use broad
Unix mode bits so processes on opposite sides of rootless Podman's UID namespace
can connect; they are reachable only through that private parent on the host and
through the explicit bind mount in the Claude container. The bridge does not
mount the Podman socket, expose a TCP listener, or provide a general
command-execution channel.

## Run with Intel or AMD graphics

```bash
mkdir -p claude-config workspace tools cache
BRIDGE_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/grotto/claude-bridge"
mkdir -p "$BRIDGE_DIR"
chmod 0777 "$BRIDGE_DIR"

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
  --volume "$BRIDGE_DIR:/run/grotto/claude-bridge:z" \
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

When `Sign in with Google` is clicked, Claude Desktop invokes the configured
browser handler inside Selkies. `/usr/local/bin/grotto-claude-browser` validates
the URL and sends it through `host.sock`. The host service opens the URL using
the host desktop's normal `xdg-open` path.

After Google and Claude finish authentication, the browser opens a `claude://`
callback. The installed host desktop entry forwards that callback through
`claude.sock`. A listener started by the Selkies autostart script inherits the
active Wayland/X11 and session D-Bus environment and passes the URI to the
running Claude Desktop application.

The shared bridge directory must be mounted for both directions to work. A
missing host socket usually means the host service is not running. A missing
Claude socket usually means the container has not reached its graphical
autostart phase. Check both with:

```bash
~/.local/bin/grotto-claude-host-bridge status
podman exec --user abc grotto-claude-desktop \
  ls -la /run/grotto/claude-bridge
```

Container-side bridge errors are written to:

```text
/config/.cache/grotto/claude-browser-bridge-error.log
/config/.cache/grotto/claude-callback-listener.log
```

Claude application state is redirected under `/config` by setting `HOME` and
the XDG paths to persistent locations. The launcher also starts the Secret
Service component of `gnome-keyring-daemon` when possible and persists its
keyring data under `/config/.local/share/keyrings`.

Treat `/config` as sensitive. It can contain authenticated sessions, Claude
settings, extension credentials, MCP configuration, and Claude Code state.

Remove the host integration with:

```bash
~/.local/bin/grotto-claude-host-bridge uninstall
```

## Persistent state

| Path | Purpose | Persistence |
| --- | --- | --- |
| `/config` | Claude sessions, settings, keyrings, and application state | Required |
| `/workspace` | Project repositories and working files | Required |
| `/tools` | User-installed tools and language environments | Recommended |
| `/cache` | Disposable package caches | Optional |
| `/run/grotto/claude-bridge` | Ephemeral host-browser and callback sockets | Runtime bind mount |

Important paths inside `/config` include:

- `/config/.claude` for Claude Code settings and state
- `/config/.claude.json` when created by Claude
- `/config/.config` for application configuration and URL-handler associations
- `/config/.cache` for application cache and bridge logs
- `/config/.local/share/keyrings` for Secret Service state

The container initialization script repairs ownership only for Grotto-managed
configuration, tool, and cache paths. It does not recursively rewrite the
mounted project workspace or host runtime directory.

## Workbench tools

The image includes a practical baseline for local development and MCP servers:
Git, GitHub CLI, SSH, curl, jq, Python, pip, ripgrep, shellcheck, SQLite,
archive tools, D-Bus utilities, and Secret Service support. It does not bundle a
web browser.

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
Selkies executable, Secret Service dependency, writable persistent roots,
bridge-client validation, callback-listener validation, HTTP/HTTPS association,
and the internal `claude://` handler. It intentionally does not launch the
graphical client, host browser, or a real authentication flow.

The remaining integration checks require an actual Selkies session and host
browser:

1. Claude renders in Wayland/Labwc and X11/Openbox modes.
2. `Sign in with Google` opens the host browser and returns to Claude.
3. Authentication survives replacement of the container.
4. File and folder selection can access `/workspace`.
5. Claude Code can edit a mounted repository and invoke installed tools.
6. Secret Service state survives restart without plaintext fallback flags.
7. The runtime works under rootless Podman without disabling SELinux or seccomp.

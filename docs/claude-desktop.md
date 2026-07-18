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

The default build tracks the current stable package candidate. A specific
version can be selected with `CLAUDE_DESKTOP_VERSION=<apt-version>`.

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

## Viewer-browser bridge

Claude Desktop delegates Google authentication to the operating system's
browser. A remote Selkies session cannot use an ordinary local browser handler
because the browser viewing the session may be on another machine.

Grotto keeps this handoff entirely inside the image:

```text
Claude Desktop
  -> xdg-open / BROWSER
  -> /usr/local/bin/grotto-claude-browser
  -> authenticated Selkies URL-event file
  -> injected Selkies viewer overlay
  -> browser-native link on the viewer's device
```

LinuxServer selects a dashboard at startup and copies it into
`/usr/share/selkies/web`, which NGINX serves through the same authentication as
the remote desktop. During the image build, Grotto patches every packaged
`selkies-dashboard*` variant with:

- `grotto-claude-viewer-open.js`, a small browser-side overlay
- `grotto-claude-open-url.json`, a writable one-event handoff file

`grotto-claude-browser` accepts only absolute HTTPS URLs, assigns each request a
unique identifier and timestamp, and writes it to the live event file. The
viewer script polls that same-origin file with caching disabled. A fresh event
shows an overlay containing a real `<a target="_blank">` link. The extra click
is intentional because browsers commonly block asynchronously created popups.

The bridge adds no browser package, host service, bind mount, TCP listener,
Podman socket, browser extension, or Selkies fork.

### Bridge security boundaries

- outbound URLs must use `https://` and include a hostname
- event URLs are limited to 16 KiB
- the viewer ignores events older than 15 minutes
- the event file is served only through the existing Selkies NGINX site
- the viewer revalidates the URL scheme before displaying it
- the overlay uses `noopener` and `noreferrer`
- no arbitrary command or non-HTTP protocol is accepted by the bridge

Anyone who can control the authenticated Selkies session can see the pending
sign-in link. Treat it as sensitive and avoid sharing a session during login.

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

When `Sign in with Google` is clicked:

1. Claude Desktop invokes the Grotto browser handler.
2. The handler publishes the HTTPS login URL into the live Selkies dashboard.
3. The browser viewing Selkies displays a `Continue Claude sign-in` overlay.
4. The user clicks `Open sign-in page` and completes authentication in that
   browser.
5. The user returns to the Selkies tab.

The outbound handoff is implemented and testable without any host integration.
The exact return behavior of Anthropic's current Linux login flow must be
observed in a real graphical session. It may complete through account-side
polling, or it may attempt a protocol callback. Grotto does not register or
forward a `claude://` callback until the actual login flow demonstrates that it
is required.

Inspect the current event inside a running container:

```bash
podman exec --user abc grotto-claude-desktop \
  cat /usr/share/selkies/web/grotto-claude-open-url.json
```

The file can contain a live authentication URL. Do not publish its contents.

Verify the browser association:

```bash
podman exec --user abc grotto-claude-desktop bash -lc '
  printf "BROWSER=%s\n" "$BROWSER"
  xdg-mime query default x-scheme-handler/https
'
```

Expected handler:

```text
grotto-claude-browser.desktop
```

Container-side handoff errors are written to:

```text
/config/.cache/grotto/claude-viewer-bridge-error.log
```

Claude application state is redirected under `/config` by setting `HOME` and
the XDG paths to persistent locations. The launcher also starts the Secret
Service component of `gnome-keyring-daemon` when possible and persists its
keyring data under `/config/.local/share/keyrings`.

Treat `/config` as sensitive. It can contain authenticated sessions, Claude
settings, extension credentials, MCP configuration, and Claude Code state.

## Persistent state

| Path | Purpose | Persistence |
| --- | --- | --- |
| `/config` | Claude sessions, settings, keyrings, and application state | Required |
| `/workspace` | Project repositories and working files | Required |
| `/tools` | User-installed tools and language environments | Recommended |
| `/cache` | Disposable package caches | Optional |

Important paths inside `/config` include:

- `/config/.claude` for Claude Code settings and state
- `/config/.claude.json` when created by Claude
- `/config/.config` for application configuration and URL-handler associations
- `/config/.cache` for application cache and viewer-bridge errors
- `/config/.local/share/keyrings` for Secret Service state

The container initialization script repairs ownership only for Grotto-managed
configuration, tool, cache, and dashboard event paths. It does not recursively
rewrite the mounted project workspace.

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
HTTPS-only browser handler, MIME association, and viewer injection across every
packaged Selkies dashboard. It intentionally does not launch the graphical
client or perform real authentication.

The remaining integration checks require an actual Selkies session:

1. Claude renders in Wayland/Labwc and X11/Openbox modes.
2. `Sign in with Google` produces the viewer overlay and opens the viewer's
   browser.
3. The post-login return behavior is identified and handled only if required.
4. Authentication survives replacement of the container.
5. File and folder selection can access `/workspace`.
6. Claude Code can edit a mounted repository and invoke installed tools.
7. Secret Service state survives restart without plaintext fallback flags.
8. The runtime works under rootless Podman without disabling SELinux or seccomp.

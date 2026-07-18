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

Grotto keeps both directions of the handoff inside the image:

```text
Claude Desktop
  -> xdg-open / BROWSER
  -> /usr/local/bin/grotto-claude-browser
  -> authenticated Selkies URL-event file
  -> injected Selkies viewer overlay
  -> browser-native sign-in link on the viewer's device
  -> copied claude:// callback
  -> same-origin Selkies POST
  -> loopback callback relay in the graphical session
  -> Claude Desktop
```

LinuxServer selects a dashboard at startup and copies it into
`/usr/share/selkies/web`, which NGINX serves through the same authentication as
the remote desktop. During the image build, Grotto patches every packaged
`selkies-dashboard*` variant with:

- `grotto-claude-viewer-open.js`, a browser-side sign-in and callback overlay
- `grotto-claude-open-url.json`, a writable one-event outbound handoff file

`grotto-claude-browser` accepts only absolute HTTPS URLs, assigns each request a
unique identifier and timestamp, and writes it to the live event file. The
viewer script polls that same-origin file with caching disabled. A fresh event
shows an overlay containing a real `<a target="_blank">` link. The extra click
is intentional because browsers commonly block asynchronously created popups.

After Google authentication, Anthropic directs the browser to a `claude://`
link. Standard web protocol-handler APIs cannot register an arbitrary custom
scheme such as `claude`, so the Selkies page cannot silently intercept that
navigation. The overlay therefore provides a callback field. The user copies
the final `Open Claude` link, returns to the Selkies tab, and either pastes it or
uses `Paste callback`.

The viewer sends that URI to `grotto/claude-callback` through the existing
Selkies origin. NGINX accepts only POST requests at that path and proxies them
to `127.0.0.1:17888`. A relay started from Claude's graphical autostart session
validates the `claude://` URI and passes it to the installed Claude Desktop
binary. Callback URIs are not written to logs or persistent storage.

The bridge adds no browser package, host service, bind mount, exposed callback
port, Podman socket, browser extension, or Selkies fork.

### Bridge security boundaries

- outbound URLs must use `https://` and include a hostname
- outbound event URLs are limited to 16 KiB
- the viewer ignores outbound events older than 15 minutes
- callback values must begin with `claude://`
- callback request bodies are limited to 64 KiB
- the callback NGINX route is POST-only and inherits Selkies authentication
- the browser request uses JSON plus `X-Grotto-Claude-Relay: 1`
- the callback relay listens only on `127.0.0.1` inside the container
- the relay does not log callback request paths or bodies
- the viewer revalidates both outbound and callback schemes
- outbound links use `noopener` and `noreferrer`
- no arbitrary command, filesystem URL, or general host-control channel is
  accepted

Anyone who can control the authenticated Selkies session can see the pending
sign-in link and submit the callback. Treat the session as sensitive and avoid
sharing it during login.

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
4. The user clicks `Open sign-in page` and completes Google authentication.
5. When the browser attempts to open Claude on the viewer device, the user
   cancels that prompt.
6. The user copies the link address from the page's `Open Claude` button.
7. The user returns to the Selkies tab and pastes the `claude://` link into the
   callback field.
8. `Send to remote Claude` forwards it through the same-origin callback relay.
9. Claude Desktop inside Selkies receives the URI and completes login.

On browsers that permit clipboard reads, `Paste callback` can fill the field
after a user gesture. Otherwise paste the copied link manually.

Inspect the current outbound event inside a running container:

```bash
podman exec --user abc grotto-claude-desktop \
  cat /usr/share/selkies/web/grotto-claude-open-url.json
```

The file can contain a live authentication URL. Do not publish its contents.

Verify the browser association and callback route:

```bash
podman exec --user abc grotto-claude-desktop bash -lc '
  printf "BROWSER=%s\n" "$BROWSER"
  xdg-mime query default x-scheme-handler/https
  grep -F "grotto/claude-callback" /etc/nginx/sites-available/default
'
```

Expected browser handler:

```text
grotto-claude-browser.desktop
```

Container-side handoff diagnostics are written to:

```text
/config/.cache/grotto/claude-viewer-bridge-error.log
/config/.cache/grotto/claude-callback-relay.log
```

The callback relay deliberately does not log submitted `claude://` values.

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
- `/config/.cache` for application cache and bridge diagnostics
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
HTTPS-only browser handler, callback relay validation, POST-only NGINX route,
MIME association, and viewer injection across every packaged Selkies dashboard.
It intentionally does not launch the graphical client or perform real
authentication.

The remaining integration checks require an actual Selkies session:

1. Claude renders in Wayland/Labwc and X11/Openbox modes.
2. `Sign in with Google` produces the viewer overlay and opens the viewer's
   browser.
3. A copied `claude://` callback completes authentication in remote Claude.
4. Authentication survives replacement of the container.
5. File and folder selection can access `/workspace`.
6. Claude Code can edit a mounted repository and invoke installed tools.
7. Secret Service state survives restart without plaintext fallback flags.
8. The runtime works under rootless Podman without disabling SELinux or seccomp.

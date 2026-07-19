# Grotto Claude Desktop

`grotto-claude-desktop` packages Anthropic's official Linux beta of Claude
Desktop in LinuxServer's Selkies base image. It is an interactive workbench,
not a Grotto worker-contract image, and does not expose workflow orchestration
or tenant policy APIs.

The image provides Claude Chat, the desktop Code interface available to eligible
plans, a mounted project workspace, persistent application state, and the same
user-managed tool and cache boundaries as the other Grotto images.

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

### X11 titlebar patch

Claude's Linux main window creates an integrated Electron titlebar containing
minimize, maximize, and close controls. Window-manager decoration rules cannot
remove those controls because they are part of the application window itself.

Grotto applies a strict build-time patch to Claude's `.vite/build/index.js`
entry inside `app.asar`. On Linux, the patched main `BrowserWindow` requests
`titleBarStyle: "default"` and disables `titleBarOverlay`. The patch must match
exactly one upstream main-window option; an upstream source change fails the
image build rather than silently restoring the controls.

The modified JavaScript file is stored through Electron's supported
`app.asar.unpacked` path. The ASAR header, size, and SHA-256 integrity metadata
are updated and verified after patching. Build details are recorded at:

```text
/usr/share/grotto/claude-titlebar-patch.json
```

Openbox then removes the resulting native frame from Claude's main window. This
two-stage policy leaves neither the application overlay controls nor an outer
window-manager titlebar, while Firefox and transient windows retain usable
window chrome.

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

## Authentication browser

Claude Desktop delegates Google authentication to the operating system's
browser. An external browser on the device viewing Selkies can complete Google
sign-in, but Anthropic's completion page then launches Claude through
JavaScript. The visible page URL remains
`https://claude.ai/login/popup-google-auth`; it does not expose a transferable
callback URL.

Because the custom application launch occurs on the browser device, a purely
external-viewer bridge cannot return it to the container without installing a
browser extension or protocol helper on that device.

Grotto therefore includes Firefox ESR as an authentication-only browser inside
the Selkies desktop:

```text
Claude Desktop
  -> xdg-open / BROWSER
  -> /usr/local/bin/grotto-claude-browser
  -> Firefox ESR inside Selkies
  -> Google authentication
  -> claude://
  -> /usr/local/bin/grotto-claude-url-handler
  -> Claude Desktop
```

`grotto-claude-browser` accepts only absolute HTTPS URLs. Firefox uses its
normal persistent profile below `/config/.mozilla`, so repeated authentication
attempts reuse browser state. The browser is not required for Claude's built-in
web search or Research features; those remain service-side Claude features.

The image registers `grotto-claude-url-handler.desktop` for the `claude://`
scheme. When Firefox asks permission to open Claude Desktop, approve the prompt.
The callback remains inside the streamed desktop and reaches the running Claude
application.

This path adds no host service, external bind mount, Podman socket, callback
port, browser extension, or Selkies fork.

### Authentication boundaries

- the browser launcher accepts only absolute `https://` URLs with a hostname
- authentication URLs are limited to 16 KiB
- only `claude://` values are accepted by the return handler
- Firefox state persists under `/config/.mozilla`
- no credentials are baked into the image
- `/config` must be treated as sensitive

## Window management

X11 with Openbox is the primary Claude runtime mode. The image defaults to:

```text
PIXELFLUX_WAYLAND=false
ELECTRON_OZONE_PLATFORM_HINT=x11
CLAUDE_NATIVE_TITLEBAR=1
ELECTRON_USE_SYSTEM_TITLE_BAR=1
```

The launcher also passes `--ozone-platform=x11` and disables Chromium's
`CustomTitlebar` feature. These launch controls complement the strict bundle
patch; they are not the sole mechanism for removing Claude's client controls.

The managed Openbox policy provides the workbench behavior:

- Claude stays true-fullscreen, undecorated, and on the bottom layer
- Claude does not reclaim focus from foreground windows
- Firefox opens windowed, focused, and above Claude
- Firefox keeps one usable titlebar instead of receiving a duplicate frame
- dialogs, utilities, and file pickers are unmaximized, raised, and focused
- LinuxServer's catch-all maximization rule is removed

The initialization script refreshes the managed Openbox configuration in the
persistent `/config` volume on every start, so replacing an older container does
not preserve stale window rules.

A Labwc policy remains packaged as a secondary Wayland compatibility path, but
X11/Openbox is the validated and documented default.

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
  --env PIXELFLUX_WAYLAND=false \
  --env AUTO_GPU=true \
  --volume "$PWD/claude-config:/config:Z" \
  --volume "$PWD/workspace:/workspace:Z" \
  --volume "$PWD/tools:/tools:Z" \
  --volume "$PWD/cache:/cache:Z" \
  ghcr.io/pelagians/grotto-claude-desktop:latest
```

Open `https://localhost:3001`. Selkies uses a self-signed certificate unless a
reverse proxy terminates TLS.

For a CPU-rendered X11 fallback, omit `/dev/dri` and use:

```bash
--env PIXELFLUX_WAYLAND=false \
--env AUTO_GPU=false \
--env ELECTRON_OZONE_PLATFORM_HINT=x11
```

## Sign in with Google

1. Click `Sign in with Google` in Claude Desktop.
2. Firefox ESR opens inside the Selkies desktop.
3. Complete Google authentication in Firefox.
4. When Firefox asks to open a `claude://` link, approve it.
5. Claude Desktop receives the callback and completes login.
6. Close Firefox after authentication if it is no longer needed.

Verify the registered handlers inside a running container:

```bash
podman exec --user abc grotto-claude-desktop bash -lc '
  printf "BROWSER=%s\n" "$BROWSER"
  xdg-mime query default x-scheme-handler/https
  xdg-mime query default x-scheme-handler/claude
'
```

Expected handlers:

```text
grotto-claude-browser.desktop
grotto-claude-url-handler.desktop
```

Browser diagnostics are written to:

```text
/config/.cache/grotto/claude-auth-browser.log
```

Claude application state is redirected under `/config` by setting `HOME` and
the XDG paths to persistent locations. The launcher also starts the Secret
Service component of `gnome-keyring-daemon` when possible and persists its
keyring data under `/config/.local/share/keyrings`.

## Persistent state

| Path | Purpose | Persistence |
| --- | --- | --- |
| `/config` | Claude sessions, settings, Firefox auth profile, keyrings, and application state | Required |
| `/workspace` | Project repositories and working files | Required |
| `/tools` | User-installed tools and language environments | Recommended |
| `/cache` | Disposable package caches | Optional |

Important paths inside `/config` include:

- `/config/.claude` for Claude Code settings and state
- `/config/.claude.json` when created by Claude
- `/config/.mozilla` for the authentication-browser profile
- `/config/.config` for application configuration and URL-handler associations
- `/config/.cache` for application and authentication-browser logs
- `/config/.local/share/keyrings` for Secret Service state

The container initialization script repairs ownership only for Grotto-managed
configuration, browser, tool, and cache paths. It does not recursively rewrite
the mounted project workspace.

## Workbench tools

The image includes Git, GitHub CLI, SSH, curl, jq, Python, pip, ripgrep,
shellcheck, SQLite, archive tools, D-Bus utilities, Secret Service support, and
Firefox ESR for authentication.

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
Selkies executable, Firefox ESR, Secret Service dependency, writable persistent
roots, HTTPS-only browser handler, `claude://` handler, MIME associations,
X11 launcher policy, titlebar patch manifest, and the patched ASAR contents. It
intentionally does not launch the graphical clients or perform real
authentication.

The remaining integration checks require an actual Selkies session:

1. Claude renders fullscreen in the primary X11/Openbox mode without any window controls.
2. Firefox, file pickers, dialogs, and utilities remain windowed and focused above Claude.
3. `Sign in with Google` opens Firefox inside Selkies.
4. Firefox returns the `claude://` callback to remote Claude.
5. Authentication survives replacement of the container.
6. File and folder selection can access `/workspace`.
7. Claude Code can edit a mounted repository and invoke installed tools.
8. Secret Service state survives restart without plaintext fallback flags.
9. The runtime works under rootless Podman without disabling SELinux or seccomp.

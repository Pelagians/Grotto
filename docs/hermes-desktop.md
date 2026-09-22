# Grotto Hermes Desktop

`ghcr.io/pelagians/grotto-hermes-desktop` packages the official Hermes Desktop Linux application from upstream tag `v2026.8.27`, commit `5fc308a70719a83cccdbba4c0e39c23f5a8239d5`, on the shared Pelagian Shell runtime.

The build uses upstream's own renderer, Electron main process, and `electron-builder` Linux `.deb` target. Grotto does not patch or reimplement Hermes Desktop.

## Boundary

```text
Pelagian Shell
  -> Grotto desktop/tool persistence
  -> official Hermes Desktop
  -> HTTP/WebSocket
  -> separately deployed grotto-hermes backend
```

Desktop never mounts backend `/opt/data` and does not start a second persistent Hermes Agent. On first launch, choose **Connect to existing Hermes** and enter the backend URL, for example `http://hermes-suite.ai.svc:9119` inside Kubernetes.

Grotto installs `/usr/local/bin/pelagian-shell-consumer` as the application
hook. It does not replace Pelagian Shell's Labwc autostart; the Shell retains
session ownership and invokes the Hermes session launcher independently.

## Persistent paths

| Path | Purpose |
| --- | --- |
| `/config` | Desktop-only Electron user data, connection registry, cookies, keyrings, and window/UI settings |
| `/workspace` | Grotto project workspace |
| `/tools` | Persistent user-installed tool environments |
| `/home/linuxbrew/.linuxbrew` | Persistent Homebrew prefix seeded from the Grotto Brewfile |
| `/cache` | Disposable package, Electron, and XDG caches |

`HERMES_DESKTOP_USER_DATA_DIR=/config/hermes-desktop` keeps client state separate from backend sessions, memory, skills, models, and execution state.

## Secret Service

The exact upstream release makes keychain encryption opt-in. Grotto enables upstream's existing `secure-token-storage.json` policy and starts GNOME Keyring through a private D-Bus session. Supply `GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD` from a Kubernetes Secret or equivalent runtime secret; it is required and is never baked into the image. Keyring data persists under `/config/.local/share/keyrings`.

For rootless Podman, create the named secret through the operator's secret
workflow, then map it to the required environment variable:

```bash
podman run \
  --secret grotto-hermes-keyring,type=env,target=GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD \
  ghcr.io/pelagians/grotto-hermes-desktop:latest
```

The equivalent Quadlet entry is:

```ini
[Container]
Image=ghcr.io/pelagians/grotto-hermes-desktop:latest
Secret=grotto-hermes-keyring,type=env,target=GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD
```

No default password is provided. Startup errors, including a missing secret,
are written to `/config/hermes-desktop/session.log` without logging the secret.

## Window policy

Hermes Desktop is multi-window software: the main window, session and browser pop-outs, authentication windows, HUD, and Quick Entry retain upstream semantics. Grotto adds no global fullscreen rule. The launcher selects native Wayland explicitly with `--enable-features=UseOzonePlatform` and `--ozone-platform=wayland`; `ELECTRON_OZONE_PLATFORM_HINT=wayland` alone is insufficient for this Hermes build. The real `/init` smoke prints the observed `wlrctl toplevel list` inventory and requires a Hermes toplevel before publication.

Pelagian Shell's daemonized Labwc adapter provides live automatic tiling, so
Grotto adds no Hermes-specific maximize/fullscreen workaround.

## Qualification

```bash
make image-hermes-desktop
GROTTO_HERMES_DESKTOP_KEYRING_PASSWORD=test-only \
  make smoke-hermes-desktop
```

The smoke starts the inherited `/init`, waits for Labwc, Pelagian autostart, GNOME Keyring, Hermes Desktop, and Selkies HTTPS, exercises shell diagnostics, prints the observed toplevel inventory, and rejects an unexpected local `hermes serve` backend.

GitHub's container runtime does not permit Electron to create the PID/network
namespace used by Chromium's sandbox. The measured failure is
`zygote_host_impl_linux.cc:207`; the container launcher therefore passes
`--no-sandbox`. This is a container-specific process-sandbox exception, not an
upstream source patch. The surrounding container, non-root `abc` user, private
streaming endpoint, and normal Grotto deployment controls remain required.

The Selkies endpoint is a remote display, so Grotto also uses upstream's
`HERMES_DESKTOP_DISABLE_GPU=1` path. This avoids Chromium GPU command-buffer
failures and remote-display flicker while leaving Selkies to encode the
software-rendered Wayland output.

### Live Shell qualification

The consumer pins the Shell image published from
`Pelagians/pelagian-shell@fe25c6756d7976322be97ece671ca8f9f9e5c7f7`
(Shell PR #7). CI checks out the shared Shell conformance harness at
`a9c6100aabc0cb79deb43910e92639f9b92b4a3d` and verifies the viewer's
SHA-256 before execution. CI starts the inherited `/init`, decodes
1920x1080 streamed frames, and checks the real application window through Labwc
IPC: healthy reconciliation, maximized usable-area geometry, visible titlebar,
and no fullscreen state. Multiwindow reflow and dialog policy remain owned and
qualified by the Shell repository.

Rootless Podman is the required runtime gate for both desktops; Hermes also
requires the Docker runtime gate. ChatGPT probes Docker compatibility and
reports its known Chromium namespace-sandbox rejection explicitly; any other
Docker failure still fails CI. Each engine uses the same built image. Tests require
native Wayland inventory and absence from the application's X11 display, then
restart the container and verify preserved configuration. Hermes also stores
and retrieves an ephemeral libsecret value across that restart on its own
session bus. These automated checks use no real account credentials; ChatGPT
login and Hermes remote-server pairing still require an authenticated user
acceptance check. No second Hermes backend is started.

Run locally with `CONTAINER_ENGINE=docker tests/smoke-chatgpt-desktop.sh` or
`CONTAINER_ENGINE=docker tests/smoke-hermes-desktop.sh`, setting the corresponding
`GROTTO_CHATGPT_DESKTOP_IMAGE` or `GROTTO_HERMES_DESKTOP_IMAGE` to the built image.

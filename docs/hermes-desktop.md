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

## Window policy

Hermes Desktop is multi-window software: the main window, session and browser pop-outs, authentication windows, HUD, and Quick Entry retain upstream semantics. Grotto adds no global fullscreen rule. The real `/init` smoke prints the observed `wlrctl toplevel list` inventory and requires a Hermes toplevel before publication. Add an application-specific one-shot main-window rule only if that measurement proves it necessary.

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

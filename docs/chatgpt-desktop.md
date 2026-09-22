# Grotto ChatGPT Desktop

`grotto-chatgpt-desktop` is a single-application interactive runtime that
streams OpenAI's official ChatGPT Desktop package for Linux through the
shared Pelagian Shell Selkies/Labwc substrate.

It is not a Grotto worker-contract image. It does not expose `grotto-workerd`
or accept orchestrator tasks. It is intended as an interactive Codex workbench
that can share a mounted project workspace with other Pelagian development
tools.

## Image construction

The image derives from a digest-pinned
`ghcr.io/pelagians/pelagian-shell@sha256:...` release, then installs OpenAI's
`chatgpt` Debian package:

1. Fetch one pinned pool artifact for the build architecture from OpenAI's
   package repository, by exact version rather than the `latest` alias.
2. Verify it against the SHA256 the repository index publishes for that
   artifact. A mismatch fails the build.
3. Install it with `apt-get`, which resolves the Electron dependency set the
   package declares.
4. Record what the installed bundle exposes in a read-only security manifest.

Pelagian Shell owns `/init`, Selkies HTTPS, Labwc, XWayland-ready defaults,
GTK appearance, window layout, and shell diagnostics. Grotto owns only
ChatGPT authentication, tool planes, application startup, and runtime tests.

Grotto installs `/usr/local/bin/pelagian-shell-consumer`, which launches the
application without replacing Shell's session autostart or Labwc policy.

Nothing is compiled, repacked, or patched, and container startup downloads
nothing.

The package supplies the Codex CLI (`/usr/lib/chatgpt/resources/codex`, exposed
on `PATH` as `codex`) and a Node runtime
(`/usr/lib/chatgpt/resources/cua_node`), so the image installs neither
separately.

### Staying on the pinned version

The vendor `postinst` normally adds OpenAI's apt source so the application
updates with the rest of the system. That would let a container drift off the
version the image was built and verified against, so the build seeds
`/etc/default/chatgpt` with `repo_add_once="false"` first and then asserts that
no `/etc/apt/sources.list.d/chatgpt.sources` was written. Moving to a new
application version is a reviewable change to the pinned build argument, not
something a running container does on its own.

### History

Earlier builds compiled the application from
[`ilysenko/codex-desktop-linux`](https://github.com/ilysenko/codex-desktop-linux),
a community wrapper that repacked the macOS DMG into a Linux Electron
application, because no native Linux build existed. Grotto patched that wrapper
to remove automatic `node_repl` JavaScript approval and to re-trust the
repacked Browser Use clients. Neither patch has an equivalent here: the vendor
bundle ships no automatic approval, and it signs its own Browser Use clients.
The build still fails if a future vendor bundle introduces automatic approval.

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
building because the package and the installed Electron application require
substantial temporary storage. That cleanup is conditional and does not run for
the smaller agent images.

Pull-request builds load the completed desktop image and run
`grotto-chatgpt-desktop-smoke` as the effective `abc` desktop user. The smoke
test checks the launch entry points and the persistent roots, confirms the
security manifest describes the package that is actually installed, and
validates that the stable `grotto-doctor --json` schema is non-invasive by
default. GitHub's Docker runner
does not validate Fedora SELinux or rootless Podman behavior; use the separate
Fedora procedure below for that boundary.

The ChatGPT Desktop package retains OpenAI's own license and distribution
terms. It is in preview for Linux, and Grotto tracks it by explicit version.

## Local build

The image is large. Keep at least 15 GiB free in the container engine's graph
store.

```bash
podman build \
  --file Containerfile.chatgpt-desktop \
  --tag localhost/grotto-chatgpt-desktop:dev \
  .
```

Override the pinned application version:

```bash
podman build \
  --file Containerfile.chatgpt-desktop \
  --build-arg CHATGPT_PACKAGE_VERSION=26.820.60940 \
  --tag localhost/grotto-chatgpt-desktop:dev \
  .
```

Component updates are intentional and reviewable:

1. Read the current version and per-architecture digests from OpenAI's package
   index, then update the Containerfile defaults and the CI matrix value
   together:

   ```bash
   base=https://persistent.oaistatic.com/codex-app-prod/linux/deb
   for arch in amd64 arm64; do
     curl -fsS "$base/dists/stable/main/binary-$arch/Packages" |
       grep -E '^(Version|SHA256):'
   done
   ```

   The version matches across architectures; the digests differ.
2. Select a qualified Pelagian Shell release and pin its manifest digest. The
   transitive Selkies digest remains recorded for provenance but is owned and
   qualified by Pelagian Shell.
3. Build the image, run `grotto-doctor --json`, and review the recorded package,
   Codex, base-image, desktop, and Electron metadata.

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

Keep `--shm-size=2g`. Chromium allocates renderer shared memory in `/dev/shm`,
and the launcher falls back to `--disable-dev-shm-usage` when the container
offers it less than 256 MiB.

Open `https://localhost:3001`. Selkies uses a self-signed certificate unless a
reverse proxy terminates TLS.

## Window behavior

The supported lane is native Wayland. Selkies starts Labwc
(`PIXELFLUX_WAYLAND=true`), the launcher asks Chromium for Wayland, and
`pelagian-layoutd` applies Shell's shared normal-window and dialog policy.
ChatGPT carries no compositor configuration or application-specific sizing
repair. One normal window fills the workspace, two normal windows tile, and
dialogs float according to the inherited Shell contract.

The launcher keeps `--class=chatgpt-desktop` as a stable application identity,
not as a selector for consumer-owned window-manager rules.

For a software-rendering fallback, omit `/dev/dri` and use:

```bash
--env AUTO_GPU=false
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
  codex login --device-auth
```

Verify the session from the same account:

```bash
podman exec \
  --user abc \
  --env HOME=/config \
  --env CODEX_HOME=/config/.codex \
  grotto-chatgpt-desktop \
  codex login status
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

Both commands collect the same static state; `--json` changes only formatting.
The default report records component versions, identity and groups, environment
paths, mount and device state, SELinux and seccomp status, user namespaces,
known Fedora compatibility, and the cached result of the most recent explicit
sandbox probe. It reports the current sandbox probe as `not_run` rather than
claiming success or failure.

Run the active Bubblewrap, devpts, protected-remount, Codex permission-profile,
and Landlock matrix only when host AVC generation is intentional:

```bash
podman exec \
  --user abc \
  --env HOME=/config \
  --env CODEX_HOME=/config/.codex \
  grotto-chatgpt-desktop \
  grotto-doctor --probe-sandbox

podman exec \
  --user abc \
  --env HOME=/config \
  --env CODEX_HOME=/config/.codex \
  grotto-chatgpt-desktop \
  grotto-doctor --probe-sandbox --json
```

The explicit option prints a warning, runs the matrix once, timestamps the
result, and updates the persistent probe cache. On the known rootless Fedora
configuration it intentionally reproduces the nested Bubblewrap SELinux AVCs.

The image build scans the installed vendor bundle and fails if it automatically
approves arbitrary `node_repl` JavaScript. The current pinned package exposes
the node_repl integration for Browser Use without automatically approving its
JavaScript tool. `grotto-doctor` reports `node_repl_exposed`,
`node_repl_auto_approved`, and `node_repl_policy_source` so this is visible
without active probes. See
[ChatGPT Desktop Browser Use policy](chatgpt-desktop-security-policy.md).

This is a containment change, not a sandbox compatibility fix. Bubblewrap-backed
command execution may remain blocked under rootless Podman with SELinux on
Fedora because fresh devpts setup and synthetic protected-path remounts fail.
Grotto does not install an automatic fallback, bind the complete outer `/dev`,
or weaken `.git`, `.agents`, or `.codex` protections. See
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

### Live Shell qualification

The consumer pins the Shell image published from
`Pelagians/pelagian-shell@fe25c6756d7976322be97ece671ca8f9f9e5c7f7`
(Shell PR #7). The smoke viewer is fetched from that same commit and verified
against its SHA-256 before execution. CI starts the inherited `/init`, decodes
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

Default Docker on the GitHub Ubuntu 24.04 runner currently rejects Chromium's
namespace sandbox with `No usable sandbox`. A nonzero
`/proc/sys/user/max_user_namespaces` does not prove that the container policy
allows creation of that namespace. The desktop launcher retains its existing
sandbox decision logic; this integration does not add sandbox bypass flags,
custom seccomp policies, capabilities, or host security-policy changes.
Rootless Podman qualification runs independently, including real application
geometry, native Wayland, restart persistence, and installed policy checks.
Default Docker desktop compatibility is not qualified. Its exact sandbox
rejection is reported as an unsupported-host result, never bypassed; other
Docker smoke failures remain errors.

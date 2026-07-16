# Grotto OpenClaw

`grotto-openclaw` is a general OpenClaw gateway image. It replaces the former communications, records, documents, and browser-specific OpenClaw images with one maintained runtime.

The OpenClaw application remains image-managed. Configuration and user-installed tools are stored outside the image.

## Storage layout

| Path | Contents | Backup policy |
| --- | --- | --- |
| `/config` | OpenClaw state, configuration, credentials, XDG state, Codex state | Back up |
| `/workspace` | Projects and files available to OpenClaw | Back up |
| `/tools` | User-installed CLIs, runtimes, and optional OpenClaw override | Rebuildable |
| `/cache` | npm, pip, uv, mise, Homebrew, and XDG caches | Disposable |

The image sets:

```text
OPENCLAW_STATE_DIR=/config/.openclaw
OPENCLAW_CONFIG_PATH=/config/.openclaw/openclaw.json
OPENCLAW_WORKSPACE_DIR=/workspace
```

## Baseline tools

The root [`Brewfile`](../Brewfile) is installed during the image build. It includes:

- shell and repository tools such as `jq`, `yq`, `ripgrep`, `fd`, `gh`, `shellcheck`, and `shfmt`
- communications tools such as Himalaya, gcalcli, vdirsyncer, khal, and khard
- data tools such as SQLite, DuckDB, and the PostgreSQL client
- document and media tools such as Pandoc, Poppler, qpdf, Tesseract, OCRmyPDF, and FFmpeg
- user-level installers such as `uv`, `pipx`, and `mise`

The baked Homebrew prefix is part of the image. Use it as the stable baseline. Persistent runtime additions should install under `/tools`.

## First launch with Podman

Create persistent volumes and a workspace:

```bash
podman volume create grotto-openclaw-config
podman volume create grotto-openclaw-tools
podman volume create grotto-openclaw-cache
mkdir -p workspace

umask 077
printf 'OPENCLAW_GATEWAY_TOKEN=%s\n' "$(openssl rand -hex 32)" > openclaw.env
```

Run onboarding against the same volumes used by the gateway:

```bash
podman run --rm -it \
  --name grotto-openclaw-onboard \
  --env-file ./openclaw.env \
  --volume grotto-openclaw-config:/config \
  --volume grotto-openclaw-tools:/tools \
  --volume grotto-openclaw-cache:/cache \
  --volume "$PWD/workspace:/workspace:Z" \
  ghcr.io/pelagians/grotto-openclaw:latest \
  openclaw onboard --mode local --no-install-daemon
```

Set container-friendly gateway defaults:

```bash
podman run --rm \
  --env-file ./openclaw.env \
  --volume grotto-openclaw-config:/config \
  --volume grotto-openclaw-tools:/tools \
  --volume grotto-openclaw-cache:/cache \
  --volume "$PWD/workspace:/workspace:Z" \
  ghcr.io/pelagians/grotto-openclaw:latest \
  openclaw config set --batch-json \
  '[{"path":"gateway.mode","value":"local"},{"path":"gateway.bind","value":"lan"},{"path":"gateway.controlUi.allowedOrigins","value":["http://localhost:18789","http://127.0.0.1:18789"]}]'
```

Start the gateway:

```bash
podman run -d \
  --name grotto-openclaw \
  --restart=unless-stopped \
  --env-file ./openclaw.env \
  --publish 18789:18789 \
  --volume grotto-openclaw-config:/config \
  --volume grotto-openclaw-tools:/tools \
  --volume grotto-openclaw-cache:/cache \
  --volume "$PWD/workspace:/workspace:Z" \
  ghcr.io/pelagians/grotto-openclaw:latest
```

Open `http://127.0.0.1:18789/` and use the token stored in `openclaw.env`.

## Docker Compose

```yaml
services:
  openclaw:
    image: ghcr.io/pelagians/grotto-openclaw:latest
    container_name: grotto-openclaw
    restart: unless-stopped
    env_file:
      - openclaw.env
    ports:
      - "18789:18789"
    volumes:
      - openclaw-config:/config
      - openclaw-tools:/tools
      - openclaw-cache:/cache
      - ./workspace:/workspace

volumes:
  openclaw-config:
  openclaw-tools:
  openclaw-cache:
```

Run onboarding and the configuration command once before `docker compose up -d`, using `docker compose run --rm openclaw ...`.

## Persistent tool installation

The following package managers write into `/tools` by default:

```bash
npm install -g some-package
pnpm add -g some-package
uv tool install some-package
pipx install some-package
mise use -g tool@version
```

Relevant locations include:

```text
/tools/bin
/tools/npm/bin
/tools/pnpm
/tools/mise
/tools/cargo/bin
```

The writable container layer is not persistent. Do not rely on runtime `apt install` or `brew install` for durable customization. Use `/tools` or build a derived image.

## Application update modes

The default mode is:

```text
GROTTO_UPDATE_MODE=image
```

In image mode, update OpenClaw by replacing the container with a newer Grotto image while retaining the four mounted paths.

An optional user-managed override can be installed into `/tools`:

```bash
podman exec -it grotto-openclaw \
  npm install -g --prefix /tools/apps/openclaw openclaw@latest
```

Then recreate the container with:

```text
GROTTO_UPDATE_MODE=user
```

The entrypoint places `/tools/apps/openclaw/bin` before the image-provided application. Removing that directory and returning to `GROTTO_UPDATE_MODE=image` restores the tested image version.

User mode is less reproducible and should be treated as locally managed.

## Updating the image

```bash
podman pull ghcr.io/pelagians/grotto-openclaw:latest
podman rm --force grotto-openclaw
```

Recreate the container with the same volume arguments. OpenClaw state and installed tools remain intact.

## Resetting installed tools

Stop the gateway, remove only the tools volume, and recreate it:

```bash
podman rm --force grotto-openclaw
podman volume rm grotto-openclaw-tools
podman volume create grotto-openclaw-tools
```

This does not remove `/config` or the workspace.

## Security boundary

- Keep `openclaw.env` private.
- Do not expose port `18789` publicly without an authenticated reverse proxy and appropriate network policy.
- Treat `/config` as sensitive because it can contain provider and channel credentials.
- Grant additional device, socket, or filesystem access only when a specific OpenClaw capability requires it.

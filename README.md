# OpenQuad

OpenQuad is a minimal appliance-style container layer for running OpenClaw under rootless Podman and Quadlet on an immutable host, with tools defined in the image and state kept outside the image.

This first milestone extends the official slim OpenClaw image with Linux Homebrew at the standard Linux prefix, `/home/linuxbrew/.linuxbrew`. Brew is baked into the image instead of installed live into a running container so the runtime stays predictable, rebuildable, and compatible with immutable-host workflows.

## Base Image

`Containerfile` uses the official slim OpenClaw image, `ghcr.io/openclaw/openclaw:slim`, through the `OPENCLAW_BASE_IMAGE` build arg. Override that arg if you need to build from a specific upstream tag or digest.

## Published Image

GitHub Actions builds and publishes the image to `ghcr.io/myos-dev/openquad` on pushes to `main`, version tags, and manual workflow runs. Pull requests build the image without publishing it.

Common tags:

```bash
podman pull ghcr.io/myos-dev/openquad:latest
podman pull ghcr.io/myos-dev/openquad:main
```

## Build

```bash
podman build -t openquad:dev -f Containerfile .
```

## Verify Brew

```bash
podman run --rm openquad:dev brew --version
podman run --rm openquad:dev sh -lc "command -v brew && brew --version"
```

## Runtime Layout

OpenQuad follows the live rootless OpenClaw layout: `/home/node/.openclaw` is the writable state boundary, `OPENCLAW_CONFIG_PATH` defaults to `/home/node/.openclaw/openclaw.json`, and caches for npm, XDG, and Codex are pointed under that state tree. The starter config is also packaged in the image at `/usr/share/openquad/defaults/openclaw.base.json5`.

The example runtime starts the gateway explicitly:

```bash
openclaw gateway --allow-unconfigured
```

For manual testing:

```bash
podman network create openquad
podman run --rm -it \
  --name openquad \
  --network openquad \
  -p 127.0.0.1:18789:18789 \
  -v openquad-state:/home/node/.openclaw \
  -v openquad-npm:/home/node/.npm \
  -v openquad-cache:/home/node/.cache \
  openquad:dev \
  openclaw gateway --allow-unconfigured
```

## Local Service Topologies

OpenQuad supports two local-service patterns. Use the shared-network pattern when you control the sibling service Quadlets. Use the host-fallback pattern when Ollama or SearXNG are already running as host-published containers or host services.

`localhost` inside the OpenQuad container means the OpenQuad container itself. It does not mean Ollama or SearXNG in another container, so avoid `http://localhost:11434` and `http://localhost:8080` for sibling services.

## Option A: Shared Podman Network

The packaged `quadlet/openquad.container` defaults to this pattern. OpenQuad, Ollama, and SearXNG join one user-defined Podman bridge network, and Podman DNS resolves service names.

```text
OLLAMA_BASE_URL=http://ollama:11434
SEARXNG_BASE_URL=http://searxng:8080
```

Use the included network unit:

```text
quadlet/openquad.network
```

Future Ollama and SearXNG Quadlets should attach to the same network with `Network=openquad.network` and stable container names such as `ContainerName=ollama` and `ContainerName=searxng`.

This is the most portable container-to-container design because it does not depend on host-published ports.

## Option B: Host-Published Fallback

If sibling services are not on the shared Podman network, point OpenQuad at the host-facing ports through `host.containers.internal`:

```bash
OLLAMA_BASE_URL=http://host.containers.internal:11434
SEARXNG_BASE_URL=http://host.containers.internal:8888
```

This matches a common rootless setup where Ollama publishes host port `11434` and SearXNG publishes host port `8888`. It is easy to adopt on an existing machine, but less portable than shared-network service discovery because the host port mapping becomes part of the runtime contract.

For this fallback, either keep the network unit installed or replace the Quadlet network line with rootless slirp networking:

```ini
Network=slirp4netns:allow_host_loopback=true
```

The example Quadlet includes commented `host.containers.internal` endpoint lines that can be uncommented for this mode.

## Endpoint Defaults

`defaults/openclaw.base.json5` is a starter config for the shared-network topology. It enables SearXNG-backed web search through `SEARXNG_BASE_URL` and includes a commented Ollama provider block using `OLLAMA_BASE_URL`; enable the Ollama block only after choosing model IDs that exist in your Ollama service.

To override endpoints without editing the template, set env vars in the Quadlet or in runtime state:

```bash
OLLAMA_BASE_URL=http://ollama:11434
SEARXNG_BASE_URL=http://searxng:8080
```

or, for host-published services:

```bash
OLLAMA_BASE_URL=http://host.containers.internal:11434
SEARXNG_BASE_URL=http://host.containers.internal:8888
```

## Quadlet Example

Rootless Quadlet examples live in `quadlet/`:

```text
quadlet/openquad.network
quadlet/openquad.container
```

Install them under `~/.config/containers/systemd/`, then run `systemctl --user daemon-reload` and start the generated services.

## Brewfile

`Brewfile` is included as the future image-layering entry point. It is intentionally empty in this milestone because the only goal here is a clean Homebrew bootstrap.

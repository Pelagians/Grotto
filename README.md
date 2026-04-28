# OpenQuad

OpenQuad is a minimal appliance-style container layer for running OpenClaw under rootless Podman and Quadlet on an immutable host, with tools defined in the image and state kept outside the image.

This first milestone extends the official slim OpenClaw image with Linux Homebrew at the standard Linux prefix, `/home/linuxbrew/.linuxbrew`. Brew is baked into the image instead of installed live into a running container so the runtime stays predictable, rebuildable, and compatible with immutable-host workflows.

## Base image

`Containerfile` is pinned to the current official slim OpenClaw image published at `ghcr.io/openclaw/openclaw:2026.4.19-beta.2-slim`.

## Published image

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

## Local service network

The preferred topology is one user-defined Podman bridge network shared by OpenQuad and local sibling services. OpenQuad should join `openquad`, Ollama should be reachable as `http://ollama:11434`, and SearXNG should be reachable as `http://searxng:8080`.

`localhost` inside the OpenQuad container means the OpenQuad container itself. It does not mean Ollama or SearXNG running in sibling containers, so avoid `http://localhost:11434` and `http://localhost:8080` for service-to-service defaults.

For manual testing:

```bash
podman network create openquad
podman run --rm -it \
  --name openquad \
  --network openquad \
  -p 127.0.0.1:18789:18789 \
  -v openquad-state:/home/node/.openclaw \
  openquad:dev
```

Future Ollama and SearXNG Quadlets should attach to the same network with `Network=openquad.network` and use `ContainerName=ollama` or `ContainerName=searxng` so Podman DNS provides stable service names.

## Endpoint defaults

`defaults/openclaw.base.json5` is a starter config for the shared-network topology. It includes a SearXNG web search endpoint using `SEARXNG_BASE_URL` and a commented Ollama provider block using `OLLAMA_BASE_URL`; enable the Ollama block only after choosing model IDs that exist in your Ollama service.

The same defaults are also present in the image at `/usr/share/openquad/defaults/openclaw.base.json5`. Runtime state still belongs under `/home/node/.openclaw`, so copy or merge the template into that state directory when initializing an OpenQuad deployment.

To override endpoints without editing the template, set env vars in the Quadlet or in `/home/node/.openclaw/.env`:

```bash
OLLAMA_BASE_URL=http://ollama:11434
SEARXNG_BASE_URL=http://searxng:8080
```

If sibling services are not on the shared Podman network, use the host fallback:

```bash
OLLAMA_BASE_URL=http://host.containers.internal:11434
SEARXNG_BASE_URL=http://host.containers.internal:8888
```

That fallback is less preferred because it depends on host-published ports instead of Podman service discovery.

## Quadlet example

Rootless Quadlet examples live in `quadlet/`:

```text
quadlet/openquad.network
quadlet/openquad.container
```

Install them under `~/.config/containers/systemd/`, then run `systemctl --user daemon-reload` and start the generated services.

## Brewfile

`Brewfile` is included as the future image-layering entry point. It is intentionally empty in this milestone because the only goal here is a clean Homebrew bootstrap.

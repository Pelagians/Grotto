# Grotto

Grotto builds and maintains standardized OCI images for AI applications, agents, and workbenches.

It packages upstream applications with reproducible builds, practical dependencies, documented storage boundaries, and deployment examples. Grotto does not provide workflow orchestration, tenant policy, approvals, or a shared agent protocol.

## Published images

| Image | Purpose |
| --- | --- |
| `ghcr.io/pelagians/grotto-openclaw:latest` | OpenClaw gateway with a broad baseline toolset and persistent user-installed tools |
| `ghcr.io/pelagians/grotto-chatgpt-desktop:latest` | Selkies-streamed ChatGPT and Codex desktop workbench |

See [`docs/image-matrix.md`](docs/image-matrix.md) for the runtime boundaries of both images.

## Grotto conventions

Grotto images keep the upstream application image-managed while separating writable state:

| Path | Purpose | Persistence |
| --- | --- | --- |
| `/config` | Credentials, sessions, and application configuration | Required |
| `/workspace` | User projects and working files | Required |
| `/tools` | User and agent-installed tools | Recommended |
| `/cache` | Package and model caches | Optional |

The application and baseline dependencies are replaced by pulling a new image. Runtime-installed tools remain in `/tools` and can be reset independently.

## OpenClaw

Build locally:

```bash
podman build \
  --file Containerfile \
  --tag localhost/grotto-openclaw:dev \
  .
```

Launch instructions, onboarding, persistent volumes, tool installation, and update modes are documented in [`docs/openclaw.md`](docs/openclaw.md).

## ChatGPT Desktop

Build locally:

```bash
podman build \
  --file Containerfile.chatgpt-desktop \
  --tag localhost/grotto-chatgpt-desktop:dev \
  .
```

See [`docs/chatgpt-desktop.md`](docs/chatgpt-desktop.md) for authentication, Selkies, storage, GPU, and security details.

## Release process

GitHub Actions builds both images on:

- pull requests targeting `main`
- pushes to `main`
- version tags
- scheduled rebuilds
- manual workflow runs

Pull requests validate both images without publishing. Other events publish branch, tag, commit-SHA, and `latest` tags according to the workflow metadata rules.

## Adding an image

A Grotto image should:

- package one identifiable upstream application
- preserve the upstream interface where practical
- define configuration, workspace, tool, and cache boundaries
- run without baked credentials
- document ports, volumes, authentication, and upgrade behavior
- avoid embedding Pelagian workflow or policy logic

## Relationship to Pelagian

- **Current** provides container-focused operating-system images.
- **Grotto** packages AI applications and workbenches.
- **Cage** packages Windows applications through Wine-compatible runtimes.
- Pelagian products may deploy these images, but Grotto remains independently usable.

## License

See [LICENSE](LICENSE) for Grotto source licensing. Packaged upstream applications retain their own licenses and distribution terms.

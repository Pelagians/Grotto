# Grotto Image Matrix

Grotto currently publishes three OCI images.

| Image | Type | Purpose | Persistent paths | Ports |
| --- | --- | --- | --- | --- |
| `ghcr.io/pelagians/grotto-openclaw:latest` | Agent application | General OpenClaw gateway with curated baseline tools and a persistent user toolchain | `/config`, `/workspace`, `/tools`, `/cache` | `18789` |
| `ghcr.io/pelagians/grotto-chatgpt-desktop:latest` | Interactive workbench | Selkies-streamed ChatGPT Desktop and Codex workspace | `/config`, `/workspace`, `/tools`, `/cache` | `3001` |
| `ghcr.io/pelagians/grotto-claude-desktop:latest` | Interactive workbench | Selkies-streamed official Claude Desktop Linux application and Code workspace | `/config`, `/workspace`, `/tools`, `/cache` | `3001` |

## Grotto OpenClaw

The image provides:

- the upstream OpenClaw gateway and CLI
- a broad build-time Brewfile
- persistent configuration and workspace paths
- a persistent, non-root user tool prefix
- image-managed and optional user-managed application modes

The image does not provide:

- a Grotto-specific worker API
- workflow orchestration
- tenant policy or approval state
- baked credentials
- automatic public-network hardening

See [`openclaw.md`](openclaw.md).

## Grotto ChatGPT Desktop

The image provides:

- ChatGPT Desktop through the Linux compatibility wrapper
- Codex CLI
- Selkies HTTPS streaming
- persistent authenticated application state
- a mounted project workspace

The image does not provide:

- OpenClaw
- workflow orchestration
- automatic organization credential provisioning
- a public internet security boundary

See [`chatgpt-desktop.md`](chatgpt-desktop.md).

## Grotto Claude Desktop

The image provides:

- Anthropic's official Claude Desktop Linux beta package
- Claude Chat and the desktop Code interface available to eligible plans
- Selkies HTTPS streaming
- persistent application, keyring, Firefox auth profile, and Claude state
- a mounted project workspace and persistent user toolchain
- Firefox ESR for Google authentication inside the Selkies desktop
- an in-container `claude://` handler that returns authentication to Claude Desktop

The image does not provide:

- a general-purpose preconfigured browsing environment
- a host-side browser service or callback daemon
- a browser extension or extra bind mount for authentication
- the separate `claude-code` CLI package
- validated Cowork KVM/QEMU passthrough
- workflow orchestration
- automatic organization credential provisioning
- a public internet security boundary

See [`claude-desktop.md`](claude-desktop.md).

# Grotto Hermes

`ghcr.io/pelagians/grotto-hermes` packages the official Hermes Agent image
(`v2026.8.27`, Hermes `0.20.6`) with Grotto's agentic tool environment.

## Runtime contract

| Path | Contents | Persistence |
| --- | --- | --- |
| `/opt/hermes` | Official Hermes application and Python/Node environment | Image-managed, read-only at runtime |
| `/opt/data` | Hermes home: config, memory, skills, sessions, plugins, cron, SQLite state | Required |
| `/workspace` | Projects and working files | Required |
| `/tools` | npm, pnpm, uv, pipx, mise, Cargo, Go tool installs | Recommended |
| `/home/linuxbrew/.linuxbrew` | Baseline and user-installed Brew formulae | Recommended; required for Brew persistence |
| `/cache` | Homebrew, npm, uv, pip, and XDG caches | Disposable |

The image does not contain Nyra, Nereus, Pontus, workflow, tenant, policy, or
approval logic.

## Ports

- `8642`: Hermes gateway
- `9119`: official Hermes dashboard

The upstream s6 entrypoint supervises Hermes services. Grotto does not add
supervisord or `nesquena/hermes-webui`.

## Homebrew persistence

The image installs the baseline from the repository `Brewfile` at build time,
then stores it as an image-owned seed archive. At startup, the seed is copied
into `/home/linuxbrew/.linuxbrew` only when that persistent prefix is empty.
After that, `brew install <formula>` writes directly to the mounted prefix as
the non-root `hermes` user. `/cache/homebrew` only holds disposable downloads.

This deliberately has a simple upgrade rule: existing user state is not
silently overwritten. To refresh the baseline, install newly required formulae
explicitly or provision a new empty Homebrew volume.

## Kubernetes storage

Mount separate PVCs (or equivalent durable volumes):

```yaml
volumeMounts:
  - {name: hermes-data, mountPath: /opt/data}
  - {name: hermes-workspace, mountPath: /workspace}
  - {name: hermes-tools, mountPath: /tools}
  - {name: hermes-homebrew, mountPath: /home/linuxbrew/.linuxbrew}
  - {name: hermes-cache, mountPath: /cache}
```

Use one Hermes writer per `/opt/data` profile. Stop the old Hermes Suite before
attaching its data PVC to this image; do not run both images concurrently.
Keep credentials in Kubernetes Secrets/environment or the existing protected
state, never in the image.

## Qualification

```bash
make image-hermes
GROTTO_HERMES_IMAGE=localhost/grotto-hermes:dev make smoke-hermes
```

The smoke test uses a disposable container and a second container against the
same temporary Homebrew directory to prove a user-installed formula survives
replacement. It is not a live-cluster migration test.

## Migration sequence

1. Back up `/opt/data` with Hermes/SQLite-aware procedures and back up `/workspace`.
2. Build and qualify the image; record the immutable image digest.
3. Create a new Deployment revision with the old PVCs, but scale the old writer to zero first.
4. Verify `hermes doctor`, dashboard, gateway, MCP connections, skills, and a test Brew install.
5. Keep the old image/PVC snapshot for rollback until the new revision passes restart and restore tests.
6. Only then change service routing or remove the old Hermes Suite resources.

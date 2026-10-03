# Hermes → Nereus agent apps (synthetic staging only)

The optional `pelagian-nereus` stdio MCP bridge is included in the Hermes image,
but is dormant unless explicitly registered in Hermes's `/opt/data/config.yaml`.
It delegates discovery, policy, approval, execution, and evidence to Nereus. It
does not hold provider credentials or implement a second policy engine.

## Prerequisites

- Apply Nereus migration `0028_agent_apps`, deploy its agent-app API, and set
  `NEREUS_SYNTHETIC_APPS_ENABLED=true` only in the qualification deployment.
- Explicitly import the reviewed `pelagian.synthetic` catalog manifest with
  `python -m app.cli.import_capability_package ../capability-catalog/examples/synthetic-package.json`,
  install it for the tenant, and mount a tenant policy allowing reads and
  requiring separate approval for writes. Do not enable the adapter in shared
  production.
- Provision one known OIDC service subject with
  `python -m app.cli.provision_app_agent --tenant-id TENANT_ID --issuer ISSUER --subject HERMES_SUBJECT --display-name "Hermes Staging"`.
  The CLI refuses role mismatches.
- Configure the identity provider to issue a short-lived bearer token for that
  subject (local) or a client-credentials token (staging). The Nereus API must
  validate the issuer, audience, and service subject normally.
- Use **synthetic data only**. Hermes conversations and tool results can persist
  in its `/opt/data` state even though Nereus audit is metadata-only.

Register the bridge in `/opt/data/config.yaml`:

```yaml
mcp_servers:
  pelagian_nereus:
    command: /opt/hermes/.venv/bin/python
    args: [/usr/local/libexec/pelagian-nereus-mcp.py]
    env:
      PELAGIAN_TENANT_ID: "${PELAGIAN_TENANT_ID}"
      PELAGIAN_NEREUS_URL: "${PELAGIAN_NEREUS_URL}"
      PELAGIAN_LOCAL_TOKEN_FILE: "${PELAGIAN_LOCAL_TOKEN_FILE}"
```

The checked-in [example config](../runtimes/hermes/nereus-mcp.example.yaml) carries this entry without credentials. Use a dedicated synthetic profile, keep only its narrow CLI toolset, and do not enable messaging platforms, terminal, file, or code-execution tools. Do not replace unrelated settings in an existing profile without review. This reduces model access to mounted secrets but is not a process-isolation boundary: the bridge and Hermes still share a container. Scope and rotate the staging client credential; real provider credentials require a separate isolation review.

Keep this entry absent to preserve current Hermes behavior. Restart or reload
Hermes MCP after changing it. Do not place tokens, client secrets, tenant IDs, or
Nereus URLs in the model-editable MCP entry; set them in the deployment
environment and read-only secret mounts. Hermes filters inherited environment
variables for MCP subprocesses, so explicitly map the reviewed variable names
under the MCP entry using `${VARIABLE}` placeholders. The local example maps
the mounted token-file path; the Kubernetes reference maps the staging OAuth
client settings.

## Authentication

For local Podman qualification, mount a short-lived token file and set
`PELAGIAN_LOCAL_TOKEN_FILE`, `PELAGIAN_NEREUS_URL` (HTTPS or loopback HTTP),
and `PELAGIAN_TENANT_ID`. The bridge rereads the token file on every request;
rotation can replace it without rebuilding the image.

For staging, omit the local token setting and set
`PELAGIAN_OAUTH_TOKEN_URL`, `PELAGIAN_OAUTH_CLIENT_ID`,
`PELAGIAN_OAUTH_CLIENT_SECRET_FILE`, `PELAGIAN_NEREUS_URL`, and
`PELAGIAN_TENANT_ID`. The Kubernetes reference sets
`PELAGIAN_OAUTH_AUDIENCE`; replace its placeholder with the registered Nereus
API audience. The secret is read from a mounted file and access tokens
are cached in memory until shortly before expiry. HTTPS is mandatory outside
loopback local qualification. The bridge never prints credentials, arguments,
results, or HTTP error bodies.

## Action flow

Hermes discovers package-qualified tool names from the active Nereus grants.
Each tool call rechecks current Nereus bindings. Reads with
`next_action=execute` execute immediately; approval- or confirmation-bound
writes return metadata-only pending receipts. Hermes can call
`pelagian_action_status(call_id)` and, after approval and user confirmation,
`pelagian_resume_action(call_id, arguments)`. The original arguments are
required again because Nereus stores only a hash, not a replayable payload.
An ambiguous write is never retried automatically.

A revoked grant or connection blocks subsequent calls immediately. The bridge
polls Nereus every 15 seconds and emits an MCP tool-list change notification
so Hermes refreshes its registry. A previously discovered name may remain in
an old conversation until that refresh; stale invocations still fail at Nereus.

## Staging deployment

`deploy/kubernetes/hermes-nereus-synthetic.yaml` is a reference, not a
production-ready cluster-specific release. Replace its image digest, PVC names,
tenant/URL values, and all three egress CIDRs with reviewed staging values.
The reference includes a dedicated ConfigMap mounted as Hermes's read-only
`/opt/data/config.yaml`; this opts the bridge in and narrows the CLI tools.
Use a dedicated synthetic profile and review any additional Hermes settings
needed before applying it. `_config_version: 39` matches the pinned Hermes
base and avoids an on-start migration attempt against the read-only file.
A `subPath` ConfigMap mount needs a pod restart to pick up changes.
Nereus's Helm Service is plain HTTP, so use a TLS gateway for the bridge; never
point its staging HTTPS URL at port 80 of the Service. The CIDRs must cover
only the approved Nereus TLS gateway, identity-provider, and model-provider
endpoints; Kubernetes NetworkPolicy cannot enforce DNS names. Use cluster
egress controls when those endpoints have dynamic IPs. Do not apply the
template with placeholder values.

Use one replica and one writer per Hermes `/opt/data` PVC. Keep the secret
volume read-only. For a fast SDK check, build
`podman build -f tests/Containerfile.nereus-bridge-smoke -t localhost/grotto-hermes-nereus-smoke:dev .`.
After the full image build, run
`GROTTO_HERMES_IMAGE=<local-image> bash tests/smoke-hermes-nereus.sh`. This checks default-disabled and opt-in Hermes configuration, including doctor, but does not connect to Nereus. Then run the
synthetic read → approval → user confirmation → resume → audit → revoke flow.
Inspect Nereus persistence/logs for absence of prompts, arguments, tokens, and
full results. No real provider adapter is in scope.

Rollback: revoke grants, disable the package and feature flag, scale Hermes
to zero. Leave additive database tables in place.

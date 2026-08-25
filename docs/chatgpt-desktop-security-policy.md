# ChatGPT Desktop Browser Use policy

Grotto installs OpenAI's native ChatGPT Desktop package for Linux at a pinned
version and applies no patches to it. The policy question is therefore what the
vendor bundle exposes, not whether a Grotto edit survived a rebuild.

During the image build, a maintained verifier scans the installed application
below `/usr/lib/chatgpt` — the packed `app.asar` archive as well as the loose
plugin scripts — and refuses to produce a manifest when it finds automatic
`node_repl` JavaScript approval (`tools.js.approval_mode = approve`). That is a
build failure, not a recorded finding. The verifier also confirms with `dpkg`
that the package is fully installed at the version the build pinned, and records
whether the Node REPL integration and Browser Use are present at all. A
successful inspection writes the read-only manifest
`/usr/share/grotto/chatgpt-desktop-security.json`.

The current pinned bundle exposes the Node REPL integration and does not
automatically approve its JavaScript tool.

`grotto-doctor` reads that manifest for the Node REPL exposure, automatic
approval, and Browser Use fields. If the manifest is missing, malformed, uses an
unsupported schema, or describes a different package version than the one the
runtime reports, the doctor reports those fields as unknown and unverified. It
does not infer a secure default. Manifests written by the pre-native images use
schema 1 and are rejected on that basis: they describe wrapper patches that no
longer exist.

## History

Earlier images built the application from the `ilysenko/codex-desktop-linux`
wrapper, which repacked the macOS DMG for Linux. Two Grotto patches applied
there and have no equivalent now:

- Removing the wrapper's insertion of `tools.js.approval_mode = approve` into
  the Browser Use MCP configuration. The vendor bundle does not insert it, and
  the scan above fails the build if a future one does.
- Rebinding trusted-client SHA-256 literals to the repacked Browser Use client
  files. The vendor ships and signs its own clients, so there is nothing to
  re-trust.

## Sandboxing is unchanged

This containment change does not alter command sandboxing. Bubblewrap-backed
command execution can remain blocked by SELinux when ChatGPT Desktop runs in a
rootless Podman container on Fedora. In that environment, ordinary commands may
still fail with denied filesystem remount and fresh `devpts` mount operations.
No external sandbox mode, unsandboxed fallback, privileged mode, `CAP_SYS_ADMIN`,
SELinux label disabling, unconfined seccomp, broad allow policy, or complete
`/dev` bind is introduced here.

The native package ships no vendored Bubblewrap helper, unlike the npm Codex CLI
the previous image installed. The image installs Debian's `bubblewrap` instead,
and `grotto-doctor` reports which helper was selected and from where.

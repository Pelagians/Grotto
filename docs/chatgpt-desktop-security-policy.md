# ChatGPT Desktop Browser Use policy

Grotto keeps the ChatGPT Desktop wrapper pinned to
`7d4049b68b17bc663b8a934326fefcaca99e8ceb` and applies a strict, repository-owned
patch before the wrapper installer runs. The patch preserves the extracted-app
Browser Use descriptor and its trusted-client SHA-256 adjustment. It removes
only the wrapper's insertion of `tools.js.approval_mode = approve` into the
Browser Use MCP configuration.

The wrapper applies Linux compatibility changes to the bundled Browser Use
clients after its Electron schema patch runs. During the image build, Grotto
therefore rebinds the schema's trusted-client literals to the SHA-256 values of
the final installed Browser and Chrome client files. The same maintained
verifier then rescans the completed application below `/opt/chatgpt`, rejects
automatic Node REPL approval, requires the trusted-client helper when Browser
Use is present, recomputes the final client hashes, and fails the build when the
bundle structure cannot be classified safely. A successful inspection writes
the read-only manifest
`/usr/share/grotto/chatgpt-desktop-security.json`.

`grotto-doctor` reads that manifest for the Node REPL exposure, automatic
approval, and Browser Use trusted-client fields. If the manifest is missing,
malformed, uses an unsupported schema, or does not match the pinned wrapper,
the doctor reports those fields as unknown and unverified. It does not infer a
secure default.

This containment change does not alter command sandboxing. Bubblewrap-backed
command execution can remain blocked by SELinux when ChatGPT Desktop runs in a
rootless Podman container on Fedora. In that environment, ordinary commands may
still fail with denied filesystem remount and fresh `devpts` mount operations.
No external sandbox mode, unsandboxed fallback, privileged mode, `CAP_SYS_ADMIN`,
SELinux label disabling, unconfined seccomp, broad allow policy, or complete
`/dev` bind is introduced here.

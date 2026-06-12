# openquad-browser-runtime-visible

Browser runtime only. No OpenClaw model, no reasoning agent, and no Homebrew appliance layer.

This image runs visible Chromium under Xvfb with VNC/noVNC support and a Chromium CDP endpoint. It is intended for login, teaching, debugging, governance, and user-assisted workflows, with one browser profile/session per pod.

## Locked mode

`VISIBLE_BROWSER_MODE=locked` is the default. Locked mode:

- starts Xvfb, x11vnc, and noVNC/websockify;
- skips the normal window manager;
- launches Chromium as the only visible application;
- starts Chromium fullscreen at `CHROMIUM_START_URL`;
- binds CDP to `CHROMIUM_CDP_HOST=0.0.0.0` and `CHROMIUM_CDP_PORT=9222` by default.

Use `VISIBLE_BROWSER_MODE=desktop` only for debugging when a minimal `fluxbox` window manager is useful.

## Browser-control endpoints

Treat CDP, VNC, and noVNC as privileged browser-control access. Do not expose them publicly. In Kubernetes, expose them only through internal Services and restrict access with NetworkPolicy.

Default ports:

- `9222`: Chromium CDP
- `5900`: VNC
- `6080`: noVNC

## Managed Chromium policy

Mount managed policy JSON at:

```text
/etc/chromium/policies/managed/
```

An example policy is provided at:

```text
templates/browser-runtime-visible/policies/vic-managed-policy.example.json
```

Use managed policy for UI/browser guardrails such as blocking `chrome://settings/*`, `chrome://extensions/*`, `chrome://flags/*`, and workflow-specific URL allowlists. Do not rely only on browser UI policy for security; VIC orchestration and agent policy must still enforce workflow permissions.

## Kubernetes profile notes

The current visible runtime should run as the Playwright `pwuser`; in the current k3s image this has been observed as UID `1001` and group `1000`. Mounted profile PVCs must be writable by that identity.

Writable paths:

- `/tmp`
- `/tmp/.X11-unix`
- `/home/pwuser/browser-profile`
- `/home/pwuser/downloads`

Use `Recreate` for persistent visible browser deployments. Do not roll two pods over the same Chromium profile PVC.

Full Chromium profiles on Ceph/RBD can be slow because Chromium writes many small cache/database files. Prefer `emptyDir` for hot cache subpaths such as:

- `/home/pwuser/browser-profile/Default/Cache`
- `/home/pwuser/browser-profile/Default/Code Cache`
- `/home/pwuser/browser-profile/Default/GPUCache`
- `/home/pwuser/browser-profile/Default/Shared Dictionary`
- `/home/pwuser/browser-profile/GPUPersistentCache`

See [`../../docs/kubernetes-vic-browser-runtime.md`](../../docs/kubernetes-vic-browser-runtime.md) for deployment examples and validation commands.

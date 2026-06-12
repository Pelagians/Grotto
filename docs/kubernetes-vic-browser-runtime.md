# Kubernetes/VIC Browser Runtime Guide

This guide documents the OpenQuad browser runtime shape for VIC teaching/governance sessions in a k3s namespace such as `ai`.

## Current design review

- `openquad-browser-agent` is the small OpenClaw agent image. It carries policy, prompt/model config, and Playwright client tooling, then connects to browser runtimes over internal networking.
- `openquad-browser-runtime-headless` remains separate and should not be disturbed by visible-runtime hardening. It exposes the headless Playwright browser server on port `3000`.
- `openquad-browser-runtime-visible` is a runtime-only image. It has no model and no reasoning agent. It runs Xvfb, x11vnc, noVNC/websockify, and Chromium.
- The visible runtime defaults to `VISIBLE_BROWSER_MODE=locked`, which launches Chromium fullscreen without a window manager, desktop panels, terminal, or general desktop menu.
- CDP is explicitly bound to `0.0.0.0:9222` for Kubernetes Service access. CDP, VNC, and noVNC are still privileged endpoints and must stay private.

## Implementation plan captured in the repo

1. Keep the existing image matrix and do not disturb the healthy headless runtime or browser agent.
2. Harden the existing visible runtime with a `VISIBLE_BROWSER_MODE=locked` default instead of creating a new image name.
3. Launch Chromium with explicit Kubernetes-friendly CDP/profile flags:
   - `--remote-debugging-address=${CHROMIUM_CDP_HOST:-0.0.0.0}`
   - `--remote-debugging-port=${CHROMIUM_CDP_PORT:-9222}`
   - `--user-data-dir=${BROWSER_PROFILE_DIR:-/home/pwuser/browser-profile}`
   - `--no-first-run`
   - `--no-default-browser-check`
   - `--disable-session-crashed-bubble`
   - `--start-fullscreen` in locked mode
4. Support managed Chromium policy by mounting JSON into `/etc/chromium/policies/managed/`.
5. Document UID/GID, PVC, cache, Service, NetworkPolicy, and validation requirements for VIC per-user/per-session pods.

## Security model

Browser-control endpoints are privileged. A caller with CDP, Playwright WebSocket, VNC, or noVNC access can control the browser session.

Required controls:

- Do not expose `9222`, `5900`, `6080`, or `3000` publicly.
- Use ClusterIP Services only.
- Restrict ingress with NetworkPolicy so only `openquad-browser-agent` and trusted VIC/control-plane components can reach browser-control endpoints.
- Use one visible browser pod/profile per VIC user/session.
- Keep raw credentials out of the agent. Prefer manual login into a persistent browser profile PVC.
- Use browser managed policy as a guardrail, not as the only security boundary.

## Managed Chromium policy

Mount a ConfigMap or other read-only volume at:

```text
/etc/chromium/policies/managed/
```

Example policy file: [`../templates/browser-runtime-visible/policies/vic-managed-policy.example.json`](../templates/browser-runtime-visible/policies/vic-managed-policy.example.json)

A minimal ConfigMap pattern:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: openquad-visible-chromium-policy
  namespace: ai
data:
  vic-managed-policy.json: |
    {
      "PasswordManagerEnabled": false,
      "AutofillAddressEnabled": false,
      "AutofillCreditCardEnabled": false,
      "ExtensionInstallBlocklist": ["*"],
      "URLBlocklist": [
        "chrome://settings/*",
        "chrome://extensions/*",
        "chrome://flags/*",
        "chrome://version/*"
      ],
      "URLAllowlist": [
        "about:blank",
        "https://example.internal/*"
      ]
    }
```

Use URL policies for workflow guardrails and domain allowlists where practical. VIC orchestration policy should still decide which workflows can navigate, fill, submit, upload, or download.

## Visible runtime Deployment and Service

Use `Recreate` when the visible runtime has a persistent Chromium profile PVC. Chromium profiles cannot safely be shared by overlapping pods.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: openquad-visible-profile-user-example
  namespace: ai
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 10Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: openquad-browser-runtime-visible
  namespace: ai
  labels:
    app: openquad-browser-runtime-visible
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: openquad-browser-runtime-visible
  template:
    metadata:
      labels:
        app: openquad-browser-runtime-visible
    spec:
      securityContext:
        runAsUser: 1001
        runAsGroup: 1000
        fsGroup: 1000
        fsGroupChangePolicy: OnRootMismatch
      initContainers:
        - name: prepare-profile
          image: busybox:1.36
          command:
            - sh
            - -ec
            - |
              mkdir -p /home/pwuser/browser-profile /home/pwuser/downloads
              rm -f \
                /home/pwuser/browser-profile/SingletonCookie \
                /home/pwuser/browser-profile/SingletonLock \
                /home/pwuser/browser-profile/SingletonSocket
              chown -R 1001:1000 /home/pwuser/browser-profile /home/pwuser/downloads
          securityContext:
            runAsUser: 0
          volumeMounts:
            - name: browser-profile
              mountPath: /home/pwuser/browser-profile
            - name: downloads
              mountPath: /home/pwuser/downloads
      containers:
        - name: visible-runtime
          image: ghcr.io/myos-dev/openquad-browser-runtime-visible:latest
          imagePullPolicy: Always
          env:
            - name: VISIBLE_BROWSER_MODE
              value: locked
            - name: CHROMIUM_CDP_HOST
              value: 0.0.0.0
            - name: CHROMIUM_CDP_PORT
              value: "9222"
            - name: CHROMIUM_START_URL
              value: about:blank
            - name: BROWSER_PROFILE_DIR
              value: /home/pwuser/browser-profile
            - name: BROWSER_DOWNLOAD_DIR
              value: /home/pwuser/downloads
          ports:
            - name: cdp
              containerPort: 9222
            - name: vnc
              containerPort: 5900
            - name: novnc
              containerPort: 6080
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            - name: x11
              mountPath: /tmp/.X11-unix
            - name: browser-profile
              mountPath: /home/pwuser/browser-profile
            - name: downloads
              mountPath: /home/pwuser/downloads
            - name: chromium-policy
              mountPath: /etc/chromium/policies/managed
              readOnly: true
            - name: cache-default
              mountPath: /home/pwuser/browser-profile/Default/Cache
            - name: code-cache-default
              mountPath: /home/pwuser/browser-profile/Default/Code Cache
            - name: gpu-cache-default
              mountPath: /home/pwuser/browser-profile/Default/GPUCache
            - name: shared-dictionary-default
              mountPath: /home/pwuser/browser-profile/Default/Shared Dictionary
            - name: gpu-persistent-cache
              mountPath: /home/pwuser/browser-profile/GPUPersistentCache
      volumes:
        - name: tmp
          emptyDir: {}
        - name: x11
          emptyDir: {}
        - name: downloads
          emptyDir: {}
        - name: browser-profile
          persistentVolumeClaim:
            claimName: openquad-visible-profile-user-example
        - name: chromium-policy
          configMap:
            name: openquad-visible-chromium-policy
            optional: true
        - name: cache-default
          emptyDir: {}
        - name: code-cache-default
          emptyDir: {}
        - name: gpu-cache-default
          emptyDir: {}
        - name: shared-dictionary-default
          emptyDir: {}
        - name: gpu-persistent-cache
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: openquad-browser-runtime-visible
  namespace: ai
spec:
  type: ClusterIP
  selector:
    app: openquad-browser-runtime-visible
  ports:
    - name: cdp
      port: 9222
      targetPort: cdp
    - name: vnc
      port: 5900
      targetPort: vnc
    - name: novnc
      port: 6080
      targetPort: novnc
```

### Ceph/RBD note

Full Chromium profiles on Ceph/RBD can be slow because Chromium performs many small writes to cache and database paths. Keep durable profile/account/session state on the PVC, but move hot cache subpaths to `emptyDir` when practical:

- `/home/pwuser/browser-profile/Default/Cache`
- `/home/pwuser/browser-profile/Default/Code Cache`
- `/home/pwuser/browser-profile/Default/GPUCache`
- `/home/pwuser/browser-profile/Default/Shared Dictionary`
- `/home/pwuser/browser-profile/GPUPersistentCache`

## Headless runtime Deployment and Service

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: openquad-browser-runtime-headless
  namespace: ai
  labels:
    app: openquad-browser-runtime-headless
spec:
  replicas: 1
  selector:
    matchLabels:
      app: openquad-browser-runtime-headless
  template:
    metadata:
      labels:
        app: openquad-browser-runtime-headless
    spec:
      containers:
        - name: headless-runtime
          image: ghcr.io/myos-dev/openquad-browser-runtime-headless:latest
          ports:
            - name: pw-ws
              containerPort: 3000
---
apiVersion: v1
kind: Service
metadata:
  name: openquad-browser-runtime-headless
  namespace: ai
spec:
  type: ClusterIP
  selector:
    app: openquad-browser-runtime-headless
  ports:
    - name: pw-ws
      port: 3000
      targetPort: pw-ws
```

## Browser agent Deployment sketch

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: openquad-browser-agent
  namespace: ai
  labels:
    app: openquad-browser-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: openquad-browser-agent
  template:
    metadata:
      labels:
        app: openquad-browser-agent
    spec:
      containers:
        - name: browser-agent
          image: ghcr.io/myos-dev/openquad-browser-agent:latest
          env:
            - name: BROWSER_WS_ENDPOINT
              value: ws://openquad-browser-runtime-headless.ai.svc.cluster.local:3000
            - name: BROWSER_CDP_ENDPOINT
              value: http://openquad-browser-runtime-visible.ai.svc.cluster.local:9222
            - name: BROWSER_DOMAIN_ALLOWLIST
              value: ""
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            - name: state
              mountPath: /home/node/.openclaw
      volumes:
        - name: tmp
          emptyDir: {}
        - name: state
          emptyDir: {}
```

## NetworkPolicy sketch

Adjust selectors for the real VIC control-plane and user-assistance UI labels. The important boundary is that browser-control endpoints are not namespace-wide or public.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: openquad-browser-runtime-visible-ingress
  namespace: ai
spec:
  podSelector:
    matchLabels:
      app: openquad-browser-runtime-visible
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: openquad-browser-agent
        - podSelector:
            matchLabels:
              app.kubernetes.io/component: vic-control-plane
      ports:
        - protocol: TCP
          port: 9222
        - protocol: TCP
          port: 5900
        - protocol: TCP
          port: 6080
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: openquad-browser-runtime-headless-ingress
  namespace: ai
spec:
  podSelector:
    matchLabels:
      app: openquad-browser-runtime-headless
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: openquad-browser-agent
        - podSelector:
            matchLabels:
              app.kubernetes.io/component: vic-control-plane
      ports:
        - protocol: TCP
          port: 3000
```

## Validation commands

Inside the visible runtime pod:

```bash
kubectl -n ai exec deploy/openquad-browser-runtime-visible -- \
  wget -qO- http://127.0.0.1:9222/json/version
```

From another pod in namespace `ai`:

```bash
kubectl -n ai run cdp-probe --rm -it --restart=Never --image=busybox:1.36 -- \
  wget -qO- http://openquad-browser-runtime-visible:9222/json/version
```

noVNC through a local port-forward:

```bash
kubectl -n ai port-forward svc/openquad-browser-runtime-visible 6080:6080
# Open http://127.0.0.1:6080/vnc.html
```

Profile/cache/database permission checks:

```bash
kubectl -n ai logs deploy/openquad-browser-runtime-visible | \
  grep -Ei 'SingletonLock|permission denied|leveldb|database|cache|profile' || true
```

Expected state:

- no `Failed to create ... SingletonLock: Permission denied` messages;
- no profile/cache/database write permission errors;
- `Failed to adjust OOM score ... Permission denied` may still appear and is usually harmless in this container context.

CDP bind check in logs:

```bash
kubectl -n ai logs deploy/openquad-browser-runtime-visible | \
  grep -E 'DevTools listening|"status":"ready"'
```

The Chrome DevTools URL should be reachable through the ClusterIP Service. If logs still show only `ws://127.0.0.1:9222/...` and Service access fails, confirm the running image contains `--remote-debugging-address=0.0.0.0` and that `CHROMIUM_CDP_HOST` was not overridden to `127.0.0.1`.

Fullscreen/browser-only visual check:

1. Port-forward noVNC on `6080`.
2. Open `http://127.0.0.1:6080/vnc.html`.
3. Confirm Chromium fills the display.
4. Confirm there are no desktop panels, no app launcher/menu, and no terminal/window-manager surface in locked mode.
5. Temporarily set `VISIBLE_BROWSER_MODE=desktop` only when debugging needs a minimal window manager.

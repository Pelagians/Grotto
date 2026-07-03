# VIC Browser-Agent Worker Deployment

This runbook deploys the OpenQuad **browser-agent worker** for the VIC Phase 1 browser screenshot proof.

It intentionally does **not** deploy an OpenQuad browser runtime. In the VIC path, browser runtime images come from `vic-web`; the OpenQuad container used here is only the bounded browser-agent executor that connects to the `vic-web` runtime Service and returns task results/artifacts to VIC Back-End.

```text
VIC Back-End/control-plane
  -> openquad-browser-agent worker
  -> vic-web Chrome runtime Service
  -> OpenQuad task result/artifacts
  -> VIC Back-End artifact/audit records
```

## Boundary

- VIC Back-End owns tasks, policy decisions, execution attempts, durable artifacts, and audit.
- OpenQuad browser-agent is a bounded executor.
- `vic-web` owns browser runtime images and runtime Helm/NetworkPolicy defaults.
- Front-End must not call OpenQuad, `vic-web`, CDP, VNC, noVNC, or Playwright directly.

## Runtime dependency

This manifest expects an existing `vic-web` Chrome headful runtime Service:

```text
vic-web-runtime-chrome-headful.vic-system.svc.cluster.local:9222
```

For a headless runtime proof, set `BROWSER_WS_ENDPOINT` instead and target the `vic-web` headless Playwright WebSocket Service on port `3000`.

## NetworkPolicy label contract

The worker pod uses:

```yaml
app.kubernetes.io/component: vic-worker
```

That label is deliberately aligned with the default `vic-web` runtime NetworkPolicy. Do not widen browser-runtime ingress namespace-wide. If a cluster uses different worker labels, use the `vic-web` Helm value `networkPolicy.extraIngressPodSelectors` with the exact trusted selector.

## Apply-ready manifest

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: openquad-browser-agent
  namespace: vic-system
  labels:
    app.kubernetes.io/name: openquad-browser-agent
    app.kubernetes.io/component: vic-worker
    app.kubernetes.io/part-of: vic
    openquad.io/template: browser-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: openquad-browser-agent
      app.kubernetes.io/component: vic-worker
  template:
    metadata:
      labels:
        app.kubernetes.io/name: openquad-browser-agent
        app.kubernetes.io/component: vic-worker
        app.kubernetes.io/part-of: vic
        openquad.io/template: browser-agent
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: openquad-browser-agent
          image: ghcr.io/myos-dev/openquad-browser-agent:latest
          imagePullPolicy: Always
          env:
            - name: OPENQUAD_WORKERD_ENABLED
              value: "true"
            - name: OPENQUAD_WORKERD_HOST
              value: 0.0.0.0
            - name: OPENQUAD_WORKERD_PORT
              value: "18789"
            - name: OPENQUAD_MANIFEST_PATH
              value: /usr/share/openquad/templates/browser-agent/openquad.manifest.json
            - name: OPENQUAD_WORKSPACE_DIR
              value: /home/node/.openclaw/workspace
            - name: BROWSER_CDP_ENDPOINT
              value: http://vic-web-runtime-chrome-headful.vic-system.svc.cluster.local:9222
          ports:
            - name: http
              containerPort: 18789
              protocol: TCP
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 6
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 20
            periodSeconds: 20
            timeoutSeconds: 2
            failureThreshold: 3
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
          volumeMounts:
            - name: workspace
              mountPath: /home/node/.openclaw/workspace
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: workspace
          emptyDir: {}
        - name: tmp
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: openquad-browser-agent
  namespace: vic-system
  labels:
    app.kubernetes.io/name: openquad-browser-agent
    app.kubernetes.io/component: vic-worker
    app.kubernetes.io/part-of: vic
    openquad.io/template: browser-agent
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: openquad-browser-agent
    app.kubernetes.io/component: vic-worker
  ports:
    - name: http
      port: 18789
      targetPort: http
      protocol: TCP
```

Copy the manifest block into `/tmp/openquad-browser-agent.yaml`, then apply it from a machine with cluster write access:

```bash
kubectl apply -f /tmp/openquad-browser-agent.yaml
kubectl -n vic-system rollout status deploy/openquad-browser-agent --timeout=180s
kubectl -n vic-system get pod,svc -l app.kubernetes.io/name=openquad-browser-agent -o wide
```

## Runtime reachability checks

From a pod carrying the same trusted worker label:

```bash
kubectl -n vic-system run openquad-cdp-probe \
  --rm -i --restart=Never \
  --image=curlimages/curl:8.8.0 \
  --labels=app.kubernetes.io/component=vic-worker \
  -- sh -ec 'curl -fsS --max-time 5 http://vic-web-runtime-chrome-headful:9222/json/version'
```

Then verify the worker daemon itself:

```bash
kubectl -n vic-system run openquad-worker-probe \
  --rm -i --restart=Never \
  --image=curlimages/curl:8.8.0 \
  -- sh -ec 'curl -fsS --max-time 5 http://openquad-browser-agent:18789/readyz && curl -fsS --max-time 5 http://openquad-browser-agent:18789/openquad/v1/manifest'
```

## VIC Back-End registration

Register or update the tenant executor with the worker Service URL:

```text
http://openquad-browser-agent.vic-system.svc.cluster.local:18789
```

Then run the Back-End manifest sync endpoint before submitting `browser.screenshot`:

```text
POST /tenants/{tenant_id}/executors/{executor_id}/sync-manifest
POST /tenants/{tenant_id}/tasks
```

Minimum task payload:

```json
{
  "task_type": "screenshot",
  "max_runtime_seconds": 60,
  "input_json": {
    "capability": "browser.screenshot",
    "url": "https://example.com/",
    "allowed_domains": ["example.com"],
    "network_policy": "restricted",
    "write_scope": "task",
    "viewport": {
      "width": 1280,
      "height": 720
    }
  }
}
```

A successful proof must show a VIC task, OpenQuad execution, a PNG artifact, and VIC audit events. A failure before artifact creation should remain a VIC task/audit failure, not a Front-End/runtime bypass.

## Known live blockers to check first

- `openquad-browser-agent` Service does not exist: Back-End submission fails with DNS `Name or service not known`.
- `vic-web-runtime-chrome-headful:9222` is not reachable: worker starts but `browser.screenshot` fails with a browser connection error.
- GHCR pull auth or image tag issue: worker pod enters `ImagePullBackOff` for `ghcr.io/myos-dev/openquad-browser-agent:latest`.

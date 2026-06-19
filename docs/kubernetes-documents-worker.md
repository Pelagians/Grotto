# Kubernetes Documents Worker Deployment

This document shows the v0.2.1 Kubernetes/local deployment path for proving VIC can route a real `documents.convert / convert_pdf_to_text` task to `openquad-documents` and receive real artifact metadata.

## Objects

The MVP deployment uses:

1. `openquad-documents` `Deployment`
2. `ClusterIP` `Service` on port `18789`
3. shared task workspace `PersistentVolumeClaim`
4. VIC executor registration using the service DNS name
5. manifest sync
6. task submission with `source_uri=file:///...`
7. artifact verification from VIC and from the shared workspace

## Shared workspace PVC

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: openquad-documents-workspace
  namespace: vic
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 10Gi
```

For single-node local clusters that do not support `ReadWriteMany`, use the local storage class your cluster provides and keep VIC and `openquad-documents` scheduled where they can both mount the same workspace. The production direction is a VIC artifact API or signed object-storage URL; this PVC handoff is only the MVP proof path.

## Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: openquad-documents
  namespace: vic
spec:
  replicas: 1
  selector:
    matchLabels:
      app: openquad-documents
  template:
    metadata:
      labels:
        app: openquad-documents
    spec:
      containers:
        - name: openquad-documents
          image: ghcr.io/myos-dev/openquad-documents:v0.2.1
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 18789
          env:
            - name: OPENQUAD_WORKERD_ENABLED
              value: "true"
            - name: OPENQUAD_WORKERD_HOST
              value: 0.0.0.0
            - name: OPENQUAD_WORKERD_PORT
              value: "18789"
            - name: OPENQUAD_WORKSPACE_DIR
              value: /home/node/.openclaw/workspace
            - name: OPENQUAD_MANIFEST_PATH
              value: /usr/share/openquad/templates/documents/openquad.manifest.json
          volumeMounts:
            - name: workspace
              mountPath: /home/node/.openclaw/workspace
      volumes:
        - name: workspace
          persistentVolumeClaim:
            claimName: openquad-documents-workspace
```

## ClusterIP Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: openquad-documents
  namespace: vic
spec:
  type: ClusterIP
  selector:
    app: openquad-documents
  ports:
    - name: http
      port: 18789
      targetPort: 18789
```

VIC should use the in-cluster service URL:

```text
http://openquad-documents.vic.svc.cluster.local:18789
```

## VIC executor registration

```bash
VIC_URL="http://vic-backend.vic.svc.cluster.local:8000"
TENANT_ID="internal"

curl -fsS \
  -H 'content-type: application/json' \
  --data '{"name":"openquad-documents","executor_type":"openquad","base_url":"http://openquad-documents.vic.svc.cluster.local:18789"}' \
  "${VIC_URL}/tenants/${TENANT_ID}/executors"
```

## Manifest sync

Replace `<executor_id>` with the ID from registration:

```bash
curl -fsS -X POST \
  "${VIC_URL}/tenants/${TENANT_ID}/executors/<executor_id>/sync-manifest"
```

The synced manifest should show `worker.name=openquad-documents`, `documents.convert`, and `convert_pdf_to_text`.

## Task submission with `source_uri=file://...`

For the MVP PVC path, VIC stages the input into the shared task workspace and submits a task with a source URI like:

```text
source_uri=file:///home/node/.openclaw/workspace/<tenant-id>/task-<task-id>/inputs/inquiry.pdf
```

Manual submission example after placing a file in the PVC at `/home/node/.openclaw/workspace/inputs/inquiry.pdf`:

```bash
curl -fsS \
  -H 'content-type: application/json' \
  --data '{
    "task_type":"convert_pdf_to_text",
    "input_json":{
      "capability":"documents.convert",
      "source_uri":"file:///home/node/.openclaw/workspace/inputs/inquiry.pdf"
    }
  }' \
  "${VIC_URL}/tenants/${TENANT_ID}/tasks"
```

Staged-source MVP example, where VIC can read the source path from the VIC backend pod filesystem and copies it into a tenant/task-scoped input directory on the shared workspace. Keep the source outside `VIC_TASK_WORKSPACE_ROOT`; sources already inside the shared workspace are rejected unless they are already inside the same tenant/task workspace.

```bash
curl -fsS \
  -H 'content-type: application/json' \
  --data '{
    "task_type":"convert_pdf_to_text",
    "input_json":{
      "capability":"documents.convert",
      "stage_source":true,
      "source_file_path":"/tmp/vic-openquad-inputs/inquiry.pdf",
      "filename":"inquiry.pdf"
    }
  }' \
  "${VIC_URL}/tenants/${TENANT_ID}/tasks"
```

## Artifact verification

In VIC, verify the returned task has:

- `status=Completed`
- `output_json.openquad_result.status=succeeded`
- `output_json.openquad_result.artifacts[]`
- `TaskArtifact` rows for `text` and `json` artifacts
- `sha256` and `size_bytes` populated

In the shared workspace, verify:

```text
/home/node/.openclaw/workspace/tasks/<openquad-task-id>/artifacts/output.txt
/home/node/.openclaw/workspace/tasks/<openquad-task-id>/artifacts/metadata.json
/home/node/.openclaw/workspace/tasks/<openquad-task-id>/artifact-manifest.json
```

The artifact verification step should compare the manifest `sha256` and `size_bytes` against the actual files.

## Known limitations

- `file://` source URIs are intentionally required for now.
- Workspace boundary validation is strict; sources outside `OPENQUAD_WORKSPACE_DIR` are rejected by the worker.
- PVC staging is the MVP path. Later milestones should replace or supplement it with a VIC artifact API or signed object-storage URLs.
- Only `openquad-documents` and `convert_pdf_to_text` are in scope for v0.2.1.
- Records, comms, browser, and LLM-backed classification remain out of scope.

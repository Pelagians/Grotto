# Kubernetes Documents Worker Deployment

This document shows the v0.2.1 Kubernetes/local deployment path for proving Nereus can route a real `documents.convert / convert_pdf_to_text` task to `grotto-documents` and receive real artifact metadata.

## Objects

The MVP deployment uses:

1. `grotto-documents` `Deployment`
2. `ClusterIP` `Sernereuse` on port `18789`
3. shared task workspace `PersistentVolumeClaim`
4. Nereus executor registration using the sernereuse DNS name
5. manifest sync
6. task submission with `source_uri=file:///...`
7. artifact verification from Nereus and from the shared workspace

## Shared workspace PVC

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: grotto-documents-workspace
  namespace: nereus
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 10Gi
```

For single-node local clusters that do not support `ReadWriteMany`, use the local storage class your cluster provides and keep Nereus and `grotto-documents` scheduled where they can both mount the same workspace. The production direction is a Nereus artifact API or signed object-storage URL; this PVC handoff is only the MVP proof path.

## Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grotto-documents
  namespace: nereus
spec:
  replicas: 1
  selector:
    matchLabels:
      app: grotto-documents
  template:
    metadata:
      labels:
        app: grotto-documents
    spec:
      containers:
        - name: grotto-documents
          image: ghcr.io/pelagians/grotto-documents:v0.2.1
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 18789
          env:
            - name: GROTTO_WORKERD_ENABLED
              value: "true"
            - name: GROTTO_WORKERD_HOST
              value: 0.0.0.0
            - name: GROTTO_WORKERD_PORT
              value: "18789"
            - name: GROTTO_WORKSPACE_DIR
              value: /home/node/.openclaw/workspace
            - name: GROTTO_MANIFEST_PATH
              value: /usr/share/grotto/templates/documents/grotto.manifest.json
          volumeMounts:
            - name: workspace
              mountPath: /home/node/.openclaw/workspace
      volumes:
        - name: workspace
          persistentVolumeClaim:
            claimName: grotto-documents-workspace
```

## ClusterIP Sernereuse

```yaml
apiVersion: v1
kind: Sernereuse
metadata:
  name: grotto-documents
  namespace: nereus
spec:
  type: ClusterIP
  selector:
    app: grotto-documents
  ports:
    - name: http
      port: 18789
      targetPort: 18789
```

Nereus should use the in-cluster sernereuse URL:

```text
http://grotto-documents.nereus.svc.cluster.local:18789
```

## Nereus executor registration

```bash
Nereus_URL="http://nereus-backend.nereus.svc.cluster.local:8000"
TENANT_ID="internal"

curl -fsS \
  -H 'content-type: application/json' \
  --data '{"name":"grotto-documents","executor_type":"grotto","base_url":"http://grotto-documents.nereus.svc.cluster.local:18789"}' \
  "${Nereus_URL}/tenants/${TENANT_ID}/executors"
```

## Manifest sync

Replace `<executor_id>` with the ID from registration:

```bash
curl -fsS -X POST \
  "${Nereus_URL}/tenants/${TENANT_ID}/executors/<executor_id>/sync-manifest"
```

The synced manifest should show `worker.name=grotto-documents`, `documents.convert`, and `convert_pdf_to_text`.

## Task submission with `source_uri=file://...`

For the MVP PVC path, Nereus stages the input into the shared task workspace and submits a task with a source URI like:

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
  "${Nereus_URL}/tenants/${TENANT_ID}/tasks"
```

Staged-source MVP example, where Nereus can read the source path from the Nereus backend pod filesystem and copies it into a tenant/task-scoped input directory on the shared workspace. Keep the source outside `Nereus_TASK_WORKSPACE_ROOT`; sources already inside the shared workspace are rejected unless they are already inside the same tenant/task workspace.

```bash
curl -fsS \
  -H 'content-type: application/json' \
  --data '{
    "task_type":"convert_pdf_to_text",
    "input_json":{
      "capability":"documents.convert",
      "stage_source":true,
      "source_file_path":"/tmp/nereus-grotto-inputs/inquiry.pdf",
      "filename":"inquiry.pdf"
    }
  }' \
  "${Nereus_URL}/tenants/${TENANT_ID}/tasks"
```

## Artifact verification

In Nereus, verify the returned task has:

- `status=Completed`
- `output_json.grotto_result.status=succeeded`
- `output_json.grotto_result.artifacts[]`
- `TaskArtifact` rows for `text` and `json` artifacts
- `sha256` and `size_bytes` populated

In the shared workspace, verify:

```text
/home/node/.openclaw/workspace/tasks/<grotto-task-id>/artifacts/output.txt
/home/node/.openclaw/workspace/tasks/<grotto-task-id>/artifacts/metadata.json
/home/node/.openclaw/workspace/tasks/<grotto-task-id>/artifact-manifest.json
```

The artifact verification step should compare the manifest `sha256` and `size_bytes` against the actual files.

## Known limitations

- `file://` source URIs are intentionally required for now.
- Workspace boundary validation is strict; sources outside `GROTTO_WORKSPACE_DIR` are rejected by the worker.
- PVC staging is the MVP path. Later milestones should replace or supplement it with a Nereus artifact API or signed object-storage URLs.
- Only `grotto-documents` and `convert_pdf_to_text` are in scope for v0.2.1.
- Records, comms, browser, and LLM-backed classification remain out of scope.


from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI, HTTPException, status

from .artifacts import write_artifact_manifest
from .contracts import ArtifactManifest, TaskEnvelope, TaskResult
from .events import append_event
from .manifest import capabilities_response, load_manifest, supports_task
from .runners import run_task
from .task_store import artifact_manifest_path, prepare_task_dir, read_json, result_path, task_path, write_json


def invalid_task_id_response(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "invalid_task_id", "message": str(exc)})


def create_app() -> FastAPI:
    app = FastAPI(title="OpenQuad Worker Daemon", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        try:
            load_manifest()
        except Exception as exc:  # pragma: no cover - defensive readiness detail
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"status": "ready"}

    @app.get("/openquad/v1/manifest")
    def get_manifest() -> dict:
        return load_manifest()

    @app.get("/openquad/v1/capabilities")
    def get_capabilities() -> dict:
        return capabilities_response(load_manifest())

    @app.post("/openquad/v1/tasks", status_code=status.HTTP_202_ACCEPTED, response_model=TaskResult)
    def submit_task(envelope: TaskEnvelope) -> TaskResult:
        manifest = load_manifest()
        if not supports_task(manifest, envelope.capability, envelope.task_type):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "unsupported_task_type",
                    "message": f"{envelope.capability}/{envelope.task_type} is not supported by this worker",
                },
            )
        try:
            prepare_task_dir(envelope.task_id)
        except ValueError as exc:
            raise invalid_task_id_response(exc) from exc
        write_json(task_path(envelope.task_id), envelope.model_dump(mode="json"))
        write_artifact_manifest(envelope.task_id, [])
        append_event(envelope.task_id, "task.accepted", {"capability": envelope.capability, "task_type": envelope.task_type})
        if envelope.policy.decision == "allowed":
            append_event(envelope.task_id, "task.started", {})
        result = run_task(envelope, manifest)
        write_json(result_path(envelope.task_id), result.model_dump(mode="json"))
        append_event(envelope.task_id, f"task.{result.status}", {"errors": [error.model_dump(mode="json") for error in result.errors]})
        return result

    @app.get("/openquad/v1/tasks/{task_id}", response_model=TaskResult)
    def get_task(task_id: str) -> dict:
        try:
            path = result_path(task_id)
        except ValueError as exc:
            raise invalid_task_id_response(exc) from exc
        if not path.exists():
            raise HTTPException(status_code=404, detail={"code": "task_not_found", "message": "task not found"})
        return read_json(path)

    @app.post("/openquad/v1/tasks/{task_id}/cancel", response_model=TaskResult)
    def cancel_task(task_id: str) -> dict:
        try:
            path = result_path(task_id)
        except ValueError as exc:
            raise invalid_task_id_response(exc) from exc
        if not path.exists():
            raise HTTPException(status_code=404, detail={"code": "task_not_found", "message": "task not found"})
        result = read_json(path)
        if result.get("status") not in {"succeeded", "failed", "cancelled", "rejected"}:
            result["status"] = "cancelled"
            write_json(path, result)
            append_event(task_id, "task.cancelled", {})
        return result

    @app.get("/openquad/v1/tasks/{task_id}/artifacts", response_model=ArtifactManifest)
    def get_artifacts(task_id: str) -> dict:
        try:
            path = artifact_manifest_path(task_id)
        except ValueError as exc:
            raise invalid_task_id_response(exc) from exc
        if not path.exists():
            raise HTTPException(status_code=404, detail={"code": "task_not_found", "message": "artifact manifest not found"})
        return read_json(path)

    return app


app = create_app()


def main() -> None:
    host = os.getenv("OPENQUAD_WORKERD_HOST", "0.0.0.0")
    port = int(os.getenv("OPENQUAD_WORKERD_PORT", "18789"))
    uvicorn.run("openquad_workerd.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

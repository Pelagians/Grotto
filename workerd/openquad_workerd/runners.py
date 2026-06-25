"""OpenQuad task runner dispatch.

Dispatches accepted task envelopes to capability-specific runners.
Unknown task types fail clearly — never pretend success.
"""

from __future__ import annotations

from typing import Any

from .contracts import TaskEnvelope, TaskError, TaskResult
from .manifest import worker_name


def run_task(envelope: TaskEnvelope, manifest: dict[str, Any]) -> TaskResult:
    """Run a task by dispatching to the appropriate capability runner.

    Policy-rejected and approval-pending tasks short-circuit before runner
    dispatch.  Known task types with real runners are delegated; all others
    fail explicitly with a clear not_implemented error.
    """

    worker = worker_name(manifest)

    if envelope.policy.decision == "rejected":
        return TaskResult(
            task_id=envelope.task_id,
            status="rejected",
            worker=worker,
            capability=envelope.capability,
            task_type=envelope.task_type,
            result={"message": "Task rejected by external policy decision."},
            policy_decision=envelope.policy,
            provenance=envelope.provenance,
            errors=[TaskError(
                code="policy_rejected",
                message=envelope.policy.reason or "Policy rejected task",
            )],
        )

    if envelope.policy.decision == "requires_approval":
        return TaskResult(
            task_id=envelope.task_id,
            status="requires_approval",
            worker=worker,
            capability=envelope.capability,
            task_type=envelope.task_type,
            result={"message": "Task requires approval from external orchestrator."},
            policy_decision=envelope.policy,
            provenance=envelope.provenance,
            errors=[TaskError(
                code="approval_required",
                message=envelope.policy.reason or "Approval required",
            )],
        )

    # -- Real capability runners ---------------------------------------------

    if envelope.capability == "documents.convert" and envelope.task_type == "convert_pdf_to_text":
        from .runners_documents import run_convert_pdf_to_text
        return run_convert_pdf_to_text(envelope, manifest)

    # -- All other task types are not yet implemented ------------------------
    return TaskResult(
        task_id=envelope.task_id,
        status="failed",
        worker=worker,
        capability=envelope.capability,
        task_type=envelope.task_type,
        result={
            "message": (
                f"No runner implemented for {envelope.capability}/{envelope.task_type}. "
                "Task type is accepted by the manifest but requires a future runner."
            ),
        },
        policy_decision=envelope.policy,
        evidence=[],
        provenance=envelope.provenance,
        artifacts=[],
        errors=[TaskError(
            code="not_implemented",
            message=f"No runner implemented for {envelope.capability}/{envelope.task_type}",
        )],
    )

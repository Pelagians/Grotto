
from __future__ import annotations

from typing import Any

from .contracts import TaskEnvelope, TaskError, TaskResult
from .manifest import worker_name


def run_task(envelope: TaskEnvelope, manifest: dict[str, Any]) -> TaskResult:
    """Run a task with the v0.1 stub runner.

    The daemon validates and records the task contract, but real connector and
    browser execution is intentionally not implemented in this first generic
    worker contract slice. Known task types therefore fail explicitly instead of
    pretending success.
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
            errors=[TaskError(code="policy_rejected", message=envelope.policy.reason or "Policy rejected task")],
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
            errors=[TaskError(code="approval_required", message=envelope.policy.reason or "Approval required")],
        )
    return TaskResult(
        task_id=envelope.task_id,
        status="failed",
        worker=worker,
        capability=envelope.capability,
        task_type=envelope.task_type,
        result={"message": "Task type is accepted by the manifest but has no concrete runner yet."},
        policy_decision=envelope.policy,
        evidence=[],
        provenance=envelope.provenance,
        artifacts=[],
        errors=[TaskError(code="not_implemented", message=f"No runner implemented for {envelope.capability}/{envelope.task_type}")],
    )

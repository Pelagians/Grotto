
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

NetworkPolicy = Literal["none", "restricted", "allowed"]
TaskStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "requires_approval",
    "rejected",
]
ArtifactKind = Literal["text", "json", "csv", "pdf", "png", "html", "trace", "screenshot", "other"]
PolicyDecisionValue = Literal["allowed", "requires_approval", "rejected"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class TaskConstraints(ContractModel):
    max_runtime_seconds: int = Field(default=300, ge=1)
    network_policy: NetworkPolicy = "restricted"
    allowed_domains: list[str] = Field(default_factory=list)
    write_scope: str = "task"


class PolicyDecision(ContractModel):
    decision: PolicyDecisionValue
    reason: str = ""
    policy_version: str = "v0.1"
    hints: dict[str, Any] = Field(default_factory=dict)


class TaskEnvelope(ContractModel):
    task_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)
    policy: PolicyDecision
    provenance: dict[str, Any] = Field(default_factory=dict)


class TaskError(ContractModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class Artifact(ContractModel):
    kind: ArtifactKind
    uri: str
    sha256: str
    size_bytes: int = Field(ge=0)
    content_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskResult(ContractModel):
    task_id: str
    status: TaskStatus
    worker: str
    capability: str
    task_type: str
    result: dict[str, Any] = Field(default_factory=dict)
    policy_decision: PolicyDecision
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)
    errors: list[TaskError] = Field(default_factory=list)


class ArtifactManifest(ContractModel):
    task_id: str
    created_at: str | None = None
    artifacts: list[Artifact] = Field(default_factory=list)

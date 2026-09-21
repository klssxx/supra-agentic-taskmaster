"""Domain Models and Data Schemas for SUPRA Agentic Taskmaster."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TaskmasterStage(str, Enum):
    """5 Canonical Stages of the Taskmaster Agent Lifecycle."""

    RECEIVED = "RECEIVED"
    STRUCTURED = "STRUCTURED"
    STRATIFIED = "STRATIFIED"
    RESTRICTED_EXECUTION_VERIFIED = "RESTRICTED_EXECUTION_VERIFIED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    @classmethod
    def _missing_(cls, value: object):
        # Read compatibility for project records written before Option B was
        # named honestly. New serialization always uses the new stage value.
        if value == "SANDBOX_VERIFIED":
            return cls.RESTRICTED_EXECUTION_VERIFIED
        return None


class Subtask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(default_factory=lambda: f"sub-{uuid.uuid4().hex[:6]}")
    title: str
    description: str
    stage_target: TaskmasterStage
    status: str = "PENDING"  # PENDING, IN_PROGRESS, COMPLETED, SKIPPED


class StructuredDecomposition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str
    core_objective: str
    invariants: list[str] = Field(default_factory=list)
    mutable_assumptions: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    subtasks: list[Subtask] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)


class StrategyCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(default_factory=lambda: f"cand-{uuid.uuid4().hex[:6]}")
    pathway_name: str
    paradigm_type: str  # CONSERVATIVE, ORTHOGONAL, LATERAL, DISRUPTIVE
    hypothesis: str
    action_plan: list[str] = Field(default_factory=list)
    divergence_score: float = 0.5
    feasibility_score: float = 0.8
    is_selected: bool = False


class VerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_id: str = Field(default_factory=lambda: f"rep-{uuid.uuid4().hex[:6]}")
    candidate_id: str
    invariants_preserved: bool = False
    invariants_checked: list[str] = Field(default_factory=list)
    vulnerabilities_detected: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    verdict: str = "NOT_EVALUATED"  # PASS, CONDITIONAL_PASS, FAIL, NOT_EVALUATED
    verification_scope: str = "STRATEGY_TEXT_COVERAGE_ONLY"
    confidence_semantics: str = "fraction_of_declared_invariants_with_textual_coverage"
    rationale: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)


class RestrictedExecutionResult(BaseModel):
    """Telemetry for trusted, in-process restricted execution.

    This model does not assert OS/process isolation and is not evidence that
    arbitrary untrusted code is safe.
    """

    model_config = ConfigDict(extra="forbid")
    execution_id: str = Field(default_factory=lambda: f"exec-{uuid.uuid4().hex[:6]}")
    candidate_id: str | None = None
    mechanism_version: str | None = None
    claim_id: str | None = None
    protocol_version: str | None = None
    observed_result: str | None = None
    action_type: str
    passed: bool
    output_log: str
    duration_ms: float
    side_effects_contained: bool = False
    execution_classification: str = "RESTRICTED_EXECUTION"
    result_scope: str = "RESTRICTED_EXECUTION_ONLY"
    scientific_validation: bool = False
    identity_bound: bool = False
    process_isolated: bool = False
    secure_for_untrusted_code: bool = False
    timestamp: float = Field(default_factory=time.time)

    @field_validator("side_effects_contained", "process_isolated", "secure_for_untrusted_code")
    @classmethod
    def reject_unproven_security_claims(cls, value: bool) -> bool:
        if value:
            raise ValueError("restricted execution cannot claim security isolation")
        return value

    @field_validator("scientific_validation")
    @classmethod
    def reject_scientific_validation_claim(cls, value: bool) -> bool:
        if value:
            raise ValueError("restricted execution cannot claim scientific validation")
        return value

    @model_validator(mode="after")
    def validate_identity_binding(self):
        if self.identity_bound and not all(
            (self.candidate_id, self.mechanism_version, self.claim_id, self.protocol_version)
        ):
            raise ValueError("identity_bound requires candidate/mechanism/claim/protocol identity")
        return self


class CheckpointRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checkpoint_id: str = Field(default_factory=lambda: f"chk-{uuid.uuid4().hex[:6]}")
    stage: TaskmasterStage
    title: str
    evidence_summary: str
    actor: str = "agent:supra:provider"
    timestamp: float = Field(default_factory=time.time)


class ProjectPosture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_execution_telemetry(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "sandbox_results" not in value:
            return value
        migrated = dict(value)
        legacy_results = migrated.pop("sandbox_results")
        migrated_results = []
        for result in legacy_results if isinstance(legacy_results, list) else []:
            if isinstance(result, dict):
                result = dict(result)
                result["side_effects_contained"] = False
                result.setdefault("execution_classification", "RESTRICTED_EXECUTION")
                result.setdefault("identity_bound", False)
                result.setdefault("process_isolated", False)
                result.setdefault("secure_for_untrusted_code", False)
            migrated_results.append(result)
        migrated["restricted_execution_results"] = migrated_results
        return migrated

    project_id: str
    objective: str
    stage: TaskmasterStage
    created_at: float
    updated_at: float
    decomposition: StructuredDecomposition | None = None
    candidates: list[StrategyCandidate] = Field(default_factory=list)
    selected_candidate: StrategyCandidate | None = None
    verification: VerificationReport | None = None
    restricted_execution_results: list[RestrictedExecutionResult] = Field(default_factory=list)
    checkpoints: list[CheckpointRecord] = Field(default_factory=list)
    final_output: dict[str, Any] | None = None
    error_message: str | None = None

"""Domain Models and Data Schemas for SUPRA Agentic Taskmaster."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RESTRICTED_EXECUTION_SEMANTICS_VERSION = 2


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
        # Legacy SANDBOX_VERIFIED cannot be promoted into the stronger current
        # execution-accreditation state. Preserve workflow progress only.
        if value == "SANDBOX_VERIFIED":
            return cls.STRATIFIED
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


def candidate_execution_identity(candidate: StrategyCandidate) -> dict[str, str]:
    """Deterministic identity of the persisted candidate mechanism/claim."""
    mechanism_payload = json.dumps(
        {
            "candidate_id": candidate.candidate_id,
            "pathway_name": candidate.pathway_name,
            "hypothesis": candidate.hypothesis,
            "action_plan": candidate.action_plan,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "candidate_id": candidate.candidate_id,
        "mechanism_version": "sha256:"
        + hashlib.sha256(mechanism_payload.encode("utf-8")).hexdigest(),
        "claim_id": "claim-"
        + hashlib.sha256(candidate.hypothesis.encode("utf-8")).hexdigest()[:24],
    }


class VerificationReport(BaseModel):
    """Scoped strategy-coverage report, not deployed-system certification."""

    model_config = ConfigDict(extra="forbid")
    report_id: str = Field(default_factory=lambda: f"rep-{uuid.uuid4().hex[:6]}")
    candidate_id: str
    invariants_preserved: bool = False
    invariants_checked: list[str] = Field(default_factory=list)
    vulnerabilities_detected: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    verdict: Literal["PASS", "CONDITIONAL_PASS", "FAIL", "NOT_EVALUATED"] = "NOT_EVALUATED"
    verification_scope: Literal["TEXTUAL_STRATEGY_COVERAGE"] = "TEXTUAL_STRATEGY_COVERAGE"
    measurement_kind: Literal["HEURISTIC_COVERAGE"] = "HEURISTIC_COVERAGE"
    confidence_semantics: str = "FRACTION_OF_DECLARED_INVARIANTS_WITH_HEURISTIC_PASS"
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
    execution_semantics_version: int | None = None
    candidate_id: str | None = None
    mechanism_version: str | None = None
    claim_id: str | None = None
    protocol_version: str | None = None
    observed_result: str | None = None
    action_type: str
    passed: bool
    output_log: str
    error_type: str | None = None
    duration_ms: float
    side_effects_contained: bool = False
    execution_classification: str = "RESTRICTED_EXECUTION"
    result_scope: str = "RESTRICTED_EXECUTION_ONLY"
    scientific_validation: bool = False
    process_isolated: bool = False
    secure_for_untrusted_code: bool = False
    identity_bound: bool = False
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
    def derive_identity_binding(self) -> RestrictedExecutionResult:
        complete = all(
            isinstance(value, str) and bool(value.strip())
            for value in (
                self.candidate_id,
                self.mechanism_version,
                self.claim_id,
                self.protocol_version,
                self.execution_id,
            )
        )
        self.identity_bound = bool(
            complete and self.execution_semantics_version == RESTRICTED_EXECUTION_SEMANTICS_VERSION
        )
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
        if not isinstance(value, dict):
            return value
        migrated = dict(value)

        if "sandbox_results" in migrated:
            legacy_results = migrated.pop("sandbox_results")
            migrated_results = []
            for result in legacy_results if isinstance(legacy_results, list) else []:
                if isinstance(result, dict):
                    result = dict(result)
                    result["side_effects_contained"] = False
                    result.setdefault("execution_classification", "RESTRICTED_EXECUTION")
                    result.setdefault("process_isolated", False)
                    result.setdefault("secure_for_untrusted_code", False)
                    result.setdefault("scientific_validation", False)
                    result.setdefault("identity_bound", False)
                migrated_results.append(result)
            migrated["restricted_execution_results"] = migrated_results

        raw_results = migrated.get("restricted_execution_results")
        has_bound_pass = False
        for result in raw_results if isinstance(raw_results, list) else []:
            if not isinstance(result, dict) or result.get("passed") is not True:
                continue
            identity_complete = all(
                isinstance(field_value := result.get(field), str) and bool(field_value.strip())
                for field in (
                    "candidate_id",
                    "mechanism_version",
                    "claim_id",
                    "protocol_version",
                    "execution_id",
                )
            )
            semantics_current = (
                result.get("execution_semantics_version") == RESTRICTED_EXECUTION_SEMANTICS_VERSION
            )
            if identity_complete and semantics_current:
                has_bound_pass = True
                break

        stage = migrated.get("stage")
        if stage in {"SANDBOX_VERIFIED", "RESTRICTED_EXECUTION_VERIFIED"} and not has_bound_pass:
            migrated["stage"] = "STRATIFIED"
            checkpoints = list(migrated.get("checkpoints") or [])
            checkpoints.append(
                {
                    "stage": "STRATIFIED",
                    "title": "Legacy execution accreditation invalidated",
                    "evidence_summary": (
                        "Persisted execution-derived stage was downgraded on load "
                        "because no bound passing execution satisfies current semantics."
                    ),
                    "actor": "system:migration_guard",
                }
            )
            migrated["checkpoints"] = checkpoints
        return migrated

    @model_validator(mode="after")
    def revalidate_persisted_execution_accreditation(self) -> ProjectPosture:
        """Revalidate execution-derived state on every load/restart.

        Workflow completion is historical and is not erased. Execution binding,
        however, is derived state: it must still match the persisted selected
        candidate under the current semantics. Cached/final-output execution
        labels are recomputed from that revalidated source state.
        """
        expected = (
            candidate_execution_identity(self.selected_candidate)
            if self.selected_candidate is not None
            else None
        )
        for result in self.restricted_execution_results:
            matches_selected_candidate = bool(
                result.identity_bound
                and expected is not None
                and result.candidate_id == expected["candidate_id"]
                and result.mechanism_version == expected["mechanism_version"]
                and result.claim_id == expected["claim_id"]
                and isinstance(result.protocol_version, str)
                and result.protocol_version.startswith("sha256:")
            )
            result.identity_bound = matches_selected_candidate

        latest_execution = (
            self.restricted_execution_results[-1] if self.restricted_execution_results else None
        )
        latest_authoritative_bound_pass = bool(
            latest_execution and latest_execution.passed and latest_execution.identity_bound
        )
        verification_allows_completion = bool(
            self.verification is not None
            and self.selected_candidate is not None
            and self.verification.candidate_id == self.selected_candidate.candidate_id
            and self.verification.verdict in {"PASS", "CONDITIONAL_PASS"}
        )
        if self.final_output is not None:
            output = dict(self.final_output)
            output["restricted_execution_identity_bound"] = bool(
                latest_execution and latest_execution.identity_bound
            )
            output["restricted_execution_status"] = (
                "BOUND_PASS"
                if latest_execution and latest_execution.passed and latest_execution.identity_bound
                else "BOUND_FAIL"
                if latest_execution and latest_execution.identity_bound
                else "UNBOUND"
                if latest_execution
                else "NOT_RUN"
            )
            output["derived_execution_state_revalidated"] = True
            self.final_output = output

        if (
            self.stage is TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED
            and not latest_authoritative_bound_pass
        ):
            self.stage = TaskmasterStage.STRATIFIED
            self.checkpoints.append(
                CheckpointRecord(
                    stage=TaskmasterStage.STRATIFIED,
                    title="Persisted execution accreditation invalidated",
                    evidence_summary=(
                        "Execution-derived stage was downgraded on load because "
                        "no current-semantics bound pass matches the persisted "
                        "selected candidate."
                    ),
                    actor="system:migration_guard",
                )
            )

        if self.stage is TaskmasterStage.COMPLETED and not (
            verification_allows_completion and latest_authoritative_bound_pass
        ):
            if latest_authoritative_bound_pass:
                repaired_stage = TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED
            elif self.selected_candidate is not None:
                repaired_stage = TaskmasterStage.STRATIFIED
            elif self.decomposition is not None:
                repaired_stage = TaskmasterStage.STRUCTURED
            else:
                repaired_stage = TaskmasterStage.RECEIVED
            self.stage = repaired_stage
            if self.final_output is not None:
                output = dict(self.final_output)
                output["workflow_status"] = "BLOCKED"
                output["completion_status"] = "BLOCKED"
                output["derived_completion_state_revalidated"] = True
                self.final_output = output
            self.checkpoints.append(
                CheckpointRecord(
                    stage=repaired_stage,
                    title="Persisted completion invalidated",
                    evidence_summary=(
                        "COMPLETED was downgraded on load because current "
                        "verification and restricted-execution completion gates "
                        "do not both pass."
                    ),
                    actor="system:migration_guard",
                )
            )
        return self

    project_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    )
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

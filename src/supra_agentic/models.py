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
SECURE_SANDBOX_SEMANTICS_VERSION = 2


class TaskmasterStage(str, Enum):
    """Canonical stages of the Taskmaster lifecycle."""

    RECEIVED = "RECEIVED"
    STRUCTURED = "STRUCTURED"
    STRATIFIED = "STRATIFIED"
    RESTRICTED_EXECUTION_VERIFIED = "RESTRICTED_EXECUTION_VERIFIED"
    SECURE_SANDBOX_VERIFIED = "SECURE_SANDBOX_VERIFIED"
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


def final_output_audit_sha256(payload: dict[str, Any]) -> str:
    """Hash the serialized final payload while excluding the hash field itself."""
    hashable = dict(payload)
    hashable.pop("audit_sha256", None)
    raw_bytes = json.dumps(hashable, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw_bytes).hexdigest()


def final_output_hash_matches(payload: dict[str, Any]) -> bool:
    """Return whether an integrity-addressed payload still matches its SHA-256."""
    recorded = payload.get("audit_sha256")
    return bool(
        isinstance(recorded, str)
        and len(recorded) == 64
        and recorded == final_output_audit_sha256(payload)
    )


def revise_final_output_payload(
    current: dict[str, Any] | None,
    updates: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any] | None:
    """Apply an authorized state revision and issue a replacement integrity hash."""
    if current is None or all(current.get(key) == value for key, value in updates.items()):
        return current
    revised = dict(current)
    previous_hash = revised.pop("audit_sha256", None)
    if isinstance(previous_hash, str):
        revised["superseded_audit_sha256"] = previous_hash
    revised.update(updates)
    revised["integrity_status"] = "CURRENT"
    revised["integrity_revision_reason"] = reason
    revised["audit_sha256"] = final_output_audit_sha256(revised)
    return revised


def invalidate_final_output_payload(
    current: dict[str, Any] | None,
    updates: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any] | None:
    """Apply load-time repairs without blessing altered bytes with a fresh hash."""
    if current is None:
        return None
    invalidated = dict(current)
    rejected_hash = invalidated.pop("audit_sha256", None)
    if isinstance(rejected_hash, str):
        invalidated["rejected_audit_sha256"] = rejected_hash
    invalidated.update(updates)
    invalidated["integrity_status"] = "INVALIDATED_BY_REVALIDATION"
    invalidated["integrity_invalidation_reason"] = reason
    return invalidated


class VerificationReport(BaseModel):
    """Scoped strategy-coverage report, not deployed-system certification."""

    model_config = ConfigDict(extra="forbid")
    report_id: str = Field(default_factory=lambda: f"rep-{uuid.uuid4().hex[:6]}")
    candidate_id: str
    mechanism_version: str | None = None
    claim_id: str | None = None
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


class SecureSandboxResult(BaseModel):
    """Receipt from an externally isolated identity-bound protocol smoke.

    The receipt establishes configured container-isolation controls and that the
    identity-bound smoke protocol executed. It does not execute the selected
    candidate mechanism, action plan, or hypothesis, and it does not claim
    scientific validation or perfect security against kernel/runtime flaws.
    """

    model_config = ConfigDict(extra="forbid")
    execution_id: str = Field(default_factory=lambda: f"sbx-{uuid.uuid4().hex[:8]}")
    execution_semantics_version: int = SECURE_SANDBOX_SEMANTICS_VERSION
    candidate_id: str | None = None
    mechanism_version: str | None = None
    claim_id: str | None = None
    protocol_version: str | None = None
    backend: Literal["docker"] = "docker"
    image: str
    image_id: str | None = None
    action_type: Literal["SECURE_CONTAINER_PYTHON"] = "SECURE_CONTAINER_PYTHON"
    execution_scope: Literal["IDENTITY_BOUNDARY_SMOKE_ONLY"] = "IDENTITY_BOUNDARY_SMOKE_ONLY"
    candidate_mechanism_executed: Literal[False] = False
    passed: bool
    observed_result: Literal["PASS", "FAIL", "UNKNOWN"]
    exit_code: int | None = None
    output_log: str = ""
    error_type: str | None = None
    duration_ms: float = Field(ge=0.0)
    timed_out: bool = False
    network_isolated: bool = False
    read_only_root: bool = False
    capabilities_dropped: bool = False
    no_new_privileges: bool = False
    non_root_user: bool = False
    resource_limits_applied: bool = False
    identity_bound: bool = False
    isolation_verified: bool = False
    security_scope: Literal["CONTAINER_ISOLATION_CONTROLS_ONLY"] = (
        "CONTAINER_ISOLATION_CONTROLS_ONLY"
    )
    scientific_validation: bool = False
    timestamp: float = Field(default_factory=time.time)

    @field_validator("scientific_validation")
    @classmethod
    def reject_scientific_validation_claim(cls, value: bool) -> bool:
        if value:
            raise ValueError("sandbox execution cannot claim scientific validation")
        return value

    @model_validator(mode="after")
    def derive_security_and_identity(self) -> SecureSandboxResult:
        identity_complete = all(
            isinstance(value, str) and bool(value.strip())
            for value in (
                self.candidate_id,
                self.mechanism_version,
                self.claim_id,
                self.protocol_version,
                self.execution_id,
            )
        )
        protocol_bound = bool(
            isinstance(self.protocol_version, str) and self.protocol_version.startswith("sha256:")
        )
        image_bound = bool(isinstance(self.image_id, str) and self.image_id.startswith("sha256:"))
        self.identity_bound = bool(
            identity_complete
            and protocol_bound
            and image_bound
            and self.execution_semantics_version == SECURE_SANDBOX_SEMANTICS_VERSION
        )
        self.isolation_verified = bool(
            self.backend == "docker"
            and image_bound
            and self.network_isolated
            and self.read_only_root
            and self.capabilities_dropped
            and self.no_new_privileges
            and self.non_root_user
            and self.resource_limits_applied
        )
        if self.passed and self.observed_result != "PASS":
            raise ValueError("passed sandbox execution must report observed_result=PASS")
        if not self.passed and self.observed_result == "PASS":
            raise ValueError("failed sandbox execution cannot report observed_result=PASS")
        if self.passed and self.timed_out:
            raise ValueError("timed out sandbox execution cannot pass")
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
        """Revalidate all completion-bearing gates on every load/restart."""
        expected = (
            candidate_execution_identity(self.selected_candidate)
            if self.selected_candidate is not None
            else None
        )

        for restricted_result in self.restricted_execution_results:
            restricted_result.identity_bound = bool(
                restricted_result.identity_bound
                and expected is not None
                and restricted_result.candidate_id == expected["candidate_id"]
                and restricted_result.mechanism_version == expected["mechanism_version"]
                and restricted_result.claim_id == expected["claim_id"]
                and isinstance(restricted_result.protocol_version, str)
                and restricted_result.protocol_version.startswith("sha256:")
            )

        for sandbox_result in self.secure_sandbox_results:
            sandbox_result.identity_bound = bool(
                sandbox_result.identity_bound
                and expected is not None
                and sandbox_result.candidate_id == expected["candidate_id"]
                and sandbox_result.mechanism_version == expected["mechanism_version"]
                and sandbox_result.claim_id == expected["claim_id"]
                and isinstance(sandbox_result.protocol_version, str)
                and sandbox_result.protocol_version.startswith("sha256:")
                and isinstance(sandbox_result.image_id, str)
                and sandbox_result.image_id.startswith("sha256:")
            )

        latest_execution = (
            self.restricted_execution_results[-1] if self.restricted_execution_results else None
        )
        latest_sandbox = self.secure_sandbox_results[-1] if self.secure_sandbox_results else None
        restricted_gate = bool(
            latest_execution and latest_execution.passed and latest_execution.identity_bound
        )
        sandbox_gate = bool(
            latest_sandbox
            and latest_sandbox.passed
            and latest_sandbox.identity_bound
            and latest_sandbox.isolation_verified
        )
        verification_gate = bool(
            self.verification is not None
            and expected is not None
            and self.verification.candidate_id == expected["candidate_id"]
            and self.verification.mechanism_version == expected["mechanism_version"]
            and self.verification.claim_id == expected["claim_id"]
            and self.verification.verdict in {"PASS", "CONDITIONAL_PASS"}
        )
        restricted_status = (
            "BOUND_PASS"
            if restricted_gate
            else "BOUND_FAIL"
            if latest_execution and latest_execution.identity_bound
            else "UNBOUND"
            if latest_execution
            else "NOT_RUN"
        )
        sandbox_status = (
            "IDENTITY_BOUND_ISOLATION_PASS"
            if sandbox_gate
            else "IDENTITY_BOUND_ISOLATION_FAIL"
            if latest_sandbox
            and latest_sandbox.identity_bound
            and latest_sandbox.isolation_verified
            else "UNVERIFIED_ISOLATION"
            if latest_sandbox
            else "NOT_RUN"
        )
        final_output_updates: dict[str, Any] = {
            "restricted_execution_identity_bound": bool(
                latest_execution and latest_execution.identity_bound
            ),
            "restricted_execution_status": restricted_status,
            "secure_sandbox_identity_bound": bool(latest_sandbox and latest_sandbox.identity_bound),
            "secure_sandbox_isolation_verified": bool(
                latest_sandbox and latest_sandbox.isolation_verified
            ),
            "secure_sandbox_execution_scope": (
                latest_sandbox.execution_scope if latest_sandbox else "NOT_RUN"
            ),
            "candidate_mechanism_executed_in_secure_sandbox": bool(
                latest_sandbox and latest_sandbox.candidate_mechanism_executed
            ),
            "secure_sandbox_status": sandbox_status,
        }
        final_output_hash_mismatch = bool(
            self.final_output is not None
            and "audit_sha256" in self.final_output
            and not final_output_hash_matches(self.final_output)
        )

        if self.stage is TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED and not restricted_gate:
            self.stage = (
                TaskmasterStage.STRATIFIED
                if self.selected_candidate is not None
                else TaskmasterStage.STRUCTURED
                if self.decomposition is not None
                else TaskmasterStage.RECEIVED
            )
            self.checkpoints.append(
                CheckpointRecord(
                    stage=self.stage,
                    title="Persisted restricted execution invalidated",
                    evidence_summary=(
                        "Restricted-execution stage was downgraded on load because "
                        "the latest current-semantics result is not a bound pass."
                    ),
                    actor="system:migration_guard",
                )
            )

        if self.stage is TaskmasterStage.SECURE_SANDBOX_VERIFIED and not sandbox_gate:
            self.stage = (
                TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED
                if restricted_gate
                else TaskmasterStage.STRATIFIED
                if self.selected_candidate is not None
                else TaskmasterStage.STRUCTURED
                if self.decomposition is not None
                else TaskmasterStage.RECEIVED
            )
            self.checkpoints.append(
                CheckpointRecord(
                    stage=self.stage,
                    title="Persisted secure sandbox accreditation invalidated",
                    evidence_summary=(
                        "Secure-sandbox stage was downgraded on load because "
                        "no identity-bound isolation smoke pass matches the selected candidate."
                    ),
                    actor="system:migration_guard",
                )
            )

        if self.stage is TaskmasterStage.COMPLETED and (
            not (verification_gate and restricted_gate and sandbox_gate)
            or final_output_hash_mismatch
        ):
            if sandbox_gate:
                repaired_stage = TaskmasterStage.SECURE_SANDBOX_VERIFIED
            elif restricted_gate:
                repaired_stage = TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED
            elif self.selected_candidate is not None:
                repaired_stage = TaskmasterStage.STRATIFIED
            elif self.decomposition is not None:
                repaired_stage = TaskmasterStage.STRUCTURED
            else:
                repaired_stage = TaskmasterStage.RECEIVED
            self.stage = repaired_stage
            final_output_updates.update(
                {
                    "workflow_status": "BLOCKED",
                    "completion_status": "BLOCKED",
                    "derived_completion_state_revalidated": True,
                }
            )
            self.checkpoints.append(
                CheckpointRecord(
                    stage=repaired_stage,
                    title="Persisted completion invalidated",
                    evidence_summary=(
                        "COMPLETED was downgraded on load because its current gates "
                        "or final-payload integrity check do not pass."
                    ),
                    actor="system:migration_guard",
                )
            )

        if self.final_output is not None:
            state_mismatch = any(
                self.final_output.get(key) != value for key, value in final_output_updates.items()
            )
            if final_output_hash_mismatch or state_mismatch:
                final_output_updates["derived_execution_state_revalidated"] = True
                reason = (
                    "PAYLOAD_HASH_MISMATCH"
                    if final_output_hash_mismatch
                    else "PERSISTED_STATE_REVALIDATION"
                )
                self.final_output = invalidate_final_output_payload(
                    self.final_output,
                    final_output_updates,
                    reason=reason,
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
    criba_dossier_receipt: dict[str, Any] | None = None
    decomposition: StructuredDecomposition | None = None
    candidates: list[StrategyCandidate] = Field(default_factory=list)
    selected_candidate: StrategyCandidate | None = None
    verification: VerificationReport | None = None
    restricted_execution_results: list[RestrictedExecutionResult] = Field(default_factory=list)
    secure_sandbox_results: list[SecureSandboxResult] = Field(default_factory=list)
    checkpoints: list[CheckpointRecord] = Field(default_factory=list)
    final_output: dict[str, Any] | None = None
    error_message: str | None = None

    @field_validator("criba_dossier_receipt")
    @classmethod
    def validate_criba_dossier_receipt(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Persist CRIBA planning input without promoting it to execution evidence."""
        if value is None:
            return None
        receipt = dict(value)
        if receipt.get("receipt_scope") != "PLANNED_DISCRIMINANT_PROTOCOL_ONLY":
            raise ValueError("CRIBA dossier receipt has invalid scope")
        if receipt.get("execution_status") != "NOT_EXECUTED":
            raise ValueError("CRIBA dossier receipt cannot claim execution")
        if receipt.get("scientific_status") != "NOT_VALIDATED":
            raise ValueError("CRIBA dossier receipt cannot claim scientific validation")
        required = (
            "criba_dossier_id",
            "criba_candidate_id",
            "claim_id",
            "mechanism_version",
            "protocol_version",
            "alternativa_explicativa",
            "intervencion_prueba",
            "observable",
            "resultado_favorable_mecanismo",
            "resultado_favorable_alternativa",
            "regla_decision",
            "condicion_fracaso",
        )
        if not all(isinstance(receipt.get(field), str) and receipt[field].strip() for field in required):
            raise ValueError("CRIBA dossier receipt is incomplete")
        return receipt

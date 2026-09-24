"""Thread-safe file-backed project state manager.

Filesystem storage is classified honestly as local, configured, or instance
ephemeral. A configured path may be durable only when the deployment mounts
a durable external backend there.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .models import (
    CheckpointRecord,
    ProjectPosture,
    RestrictedExecutionResult,
    SecureSandboxResult,
    StrategyCandidate,
    StructuredDecomposition,
    TaskmasterStage,
    VerificationReport,
    candidate_execution_identity,
    final_output_audit_sha256,
    revise_final_output_payload,
)

logger = logging.getLogger("supra_agentic.state")
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class CompletionGateError(RuntimeError):
    """Raised when workflow completion lacks required independent gate evidence."""


class ProjectTerminalStateError(RuntimeError):
    """Raised when callers try to replay a terminally failed project in place."""


def validate_project_id(project_id: str) -> str:
    """Validate the storage identity before any filesystem path is constructed."""
    if not isinstance(project_id, str) or not PROJECT_ID_RE.fullmatch(project_id):
        raise ValueError("project_id must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    return project_id


def _verification_matches_identity(
    report: VerificationReport | None,
    expected: dict[str, str] | None,
) -> bool:
    return bool(
        report is not None
        and expected is not None
        and report.candidate_id == expected["candidate_id"]
        and report.mechanism_version == expected["mechanism_version"]
        and report.claim_id == expected["claim_id"]
    )


def _restricted_matches_identity(
    result: RestrictedExecutionResult | None,
    expected: dict[str, str] | None,
) -> bool:
    return bool(
        result is not None
        and result.identity_bound
        and expected is not None
        and result.candidate_id == expected["candidate_id"]
        and result.mechanism_version == expected["mechanism_version"]
        and result.claim_id == expected["claim_id"]
        and isinstance(result.protocol_version, str)
        and result.protocol_version.startswith("sha256:")
    )


def _sandbox_matches_identity(
    result: SecureSandboxResult | None,
    expected: dict[str, str] | None,
) -> bool:
    return bool(
        result is not None
        and result.identity_bound
        and expected is not None
        and result.candidate_id == expected["candidate_id"]
        and result.mechanism_version == expected["mechanism_version"]
        and result.claim_id == expected["claim_id"]
        and isinstance(result.protocol_version, str)
        and result.protocol_version.startswith("sha256:")
        and isinstance(result.image_id, str)
        and result.image_id.startswith("sha256:")
    )


def _get_storage_configuration(
    explicit: Path | str | None = None,
) -> tuple[Path, str]:
    """Resolve filesystem location without claiming unverified durability."""
    if explicit is not None:
        return Path(explicit), "CONFIGURED_FILESYSTEM"
    for env_var in ("SUPRA_STORAGE_DIR", "CLOUD_RUN_PERSISTENT_DIR"):
        if path := os.getenv(env_var):
            return Path(path), "CONFIGURED_FILESYSTEM"
    if os.getenv("K_SERVICE"):
        return Path(tempfile.gettempdir()) / "supra-agentic", "INSTANCE_EPHEMERAL"
    if os.name == "nt":
        root = Path(os.getenv("LOCALAPPDATA", tempfile.gettempdir()))
        return root / "SUPRA-Agentic", "LOCAL_FILESYSTEM"
    return Path.home() / ".supra" / "projects", "LOCAL_FILESYSTEM"


class ProjectStateManager:
    """Manage project lifecycles with locked filesystem persistence."""

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        self._lock = threading.RLock()
        self._projects: dict[str, ProjectPosture] = {}
        self.storage_dir, self.storage_mode = _get_storage_configuration(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_project(self, objective: str, project_id: str | None = None) -> ProjectPosture:
        """Create a new project session in RECEIVED stage."""
        with self._lock:
            pid = validate_project_id(project_id or f"proj-{uuid.uuid4().hex[:8]}")
            if pid in self._projects or (self.storage_dir / f"{pid}.json").exists():
                raise ValueError(f"Project '{pid}' already exists.")
            now = time.time()
            posture = ProjectPosture(
                project_id=pid,
                objective=objective.strip(),
                stage=TaskmasterStage.RECEIVED,
                created_at=now,
                updated_at=now,
                checkpoints=[
                    CheckpointRecord(
                        stage=TaskmasterStage.RECEIVED,
                        title="Project Initialized",
                        evidence_summary=f"Objective registered: '{objective[:100]}...'",
                        actor="system:session_manager",
                    )
                ],
            )
            self._projects[pid] = posture
            self._persist_or_restore(pid, previous=None)
            return posture

    def get_project(self, project_id: str) -> ProjectPosture | None:
        """Retrieve a project state by ID."""
        project_id = validate_project_id(project_id)
        with self._lock:
            if project_id in self._projects:
                return self._projects[project_id]
            # Try to load from disk
            p_file = self.storage_dir / f"{project_id}.json"
            if p_file.exists():
                try:
                    data = json.loads(p_file.read_text(encoding="utf-8"))
                    posture = ProjectPosture.model_validate(data)
                    if posture.project_id != project_id:
                        raise ValueError("persisted project_id does not match its filename")
                    self._projects[project_id] = posture
                    return posture
                except Exception as exc:
                    logger.error(
                        "Failed to load project %s from disk (%s)",
                        project_id,
                        type(exc).__name__,
                    )
            return None

    def update_decomposition(
        self, project_id: str, decomp: StructuredDecomposition
    ) -> ProjectPosture:
        """Store decomposition and advance stage to STRUCTURED."""
        with self._lock:
            p = self._get_mutable_project(project_id)
            previous = p.model_copy(deep=True)
            p.decomposition = decomp
            p.stage = TaskmasterStage.STRUCTURED
            p.updated_at = time.time()
            p.checkpoints.append(
                CheckpointRecord(
                    stage=TaskmasterStage.STRUCTURED,
                    title="Objective Structured",
                    evidence_summary=f"Decomposed into {len(decomp.invariants)} invariants, {len(decomp.mutable_assumptions)} mutable assumptions, and {len(decomp.subtasks)} subtasks.",
                    actor="agent:supra:decompose",
                )
            )
            self._persist_or_restore(project_id, previous)
            return p

    def add_candidates(
        self, project_id: str, candidates: list[StrategyCandidate], select_best: bool = True
    ) -> ProjectPosture:
        """Store strategy candidates and advance stage to STRATIFIED."""
        with self._lock:
            p = self._get_mutable_project(project_id)
            previous = p.model_copy(deep=True)
            previous_identity = (
                candidate_execution_identity(p.selected_candidate)
                if p.selected_candidate is not None
                else None
            )
            p.candidates = candidates
            if select_best and candidates:
                # Select candidate with highest combined feasibility + divergence score
                best = max(
                    candidates, key=lambda c: c.feasibility_score * 0.6 + c.divergence_score * 0.4
                )
                best.is_selected = True
                p.selected_candidate = best

            current_identity = (
                candidate_execution_identity(p.selected_candidate)
                if p.selected_candidate is not None
                else None
            )
            if previous_identity is not None and previous_identity != current_identity:
                if not _verification_matches_identity(p.verification, current_identity):
                    p.verification = None
                if p.final_output is not None:
                    p.final_output = revise_final_output_payload(
                        p.final_output,
                        {
                            "workflow_status": "BLOCKED",
                            "completion_status": "BLOCKED",
                            "derived_completion_state_revalidated": True,
                        },
                        reason="SELECTED_CANDIDATE_IDENTITY_CHANGED",
                    )

            p.stage = TaskmasterStage.STRATIFIED
            p.updated_at = time.time()
            sel_name = p.selected_candidate.pathway_name if p.selected_candidate else "None"
            p.checkpoints.append(
                CheckpointRecord(
                    stage=TaskmasterStage.STRATIFIED,
                    title="Strategies Synthesized",
                    evidence_summary=f"Generated {len(candidates)} strategic candidates. Selected primary pathway: '{sel_name}'.",
                    actor="agent:supra:strategy",
                )
            )
            self._persist_or_restore(project_id, previous)
            return p

    def record_verification(self, project_id: str, report: VerificationReport) -> ProjectPosture:
        """Store verification report."""
        with self._lock:
            p = self._get_mutable_project(project_id)
            previous = p.model_copy(deep=True)
            expected = (
                candidate_execution_identity(p.selected_candidate)
                if p.selected_candidate is not None
                else None
            )
            if not _verification_matches_identity(report, expected):
                raise ValueError(
                    "verification report identity does not match the selected candidate mechanism"
                )
            p.verification = report
            latest_execution = (
                p.restricted_execution_results[-1] if p.restricted_execution_results else None
            )
            latest_sandbox = p.secure_sandbox_results[-1] if p.secure_sandbox_results else None
            restricted_gate = bool(
                latest_execution
                and latest_execution.passed
                and _restricted_matches_identity(latest_execution, expected)
            )
            sandbox_gate = bool(
                latest_sandbox
                and latest_sandbox.passed
                and _sandbox_matches_identity(latest_sandbox, expected)
                and latest_sandbox.isolation_verified
            )
            verification_gate = report.verdict in {"PASS", "CONDITIONAL_PASS"}
            completion_revoked = p.stage is TaskmasterStage.COMPLETED and not verification_gate
            if completion_revoked:
                p.stage = (
                    TaskmasterStage.SECURE_SANDBOX_VERIFIED
                    if sandbox_gate
                    else TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED
                    if restricted_gate
                    else TaskmasterStage.STRATIFIED
                )

            if p.final_output is not None:
                provenance_raw = p.final_output.get("evidence_provenance")
                provenance = dict(provenance_raw) if isinstance(provenance_raw, dict) else {}
                provenance["verification_report_id"] = report.report_id
                updates: dict[str, Any] = {
                    "verification_verdict": report.verdict,
                    "evidence_provenance": provenance,
                }
                if completion_revoked:
                    updates.update(
                        {
                            "workflow_status": "BLOCKED",
                            "completion_status": "BLOCKED",
                            "derived_completion_state_revalidated": True,
                        }
                    )
                p.final_output = revise_final_output_payload(
                    p.final_output,
                    updates,
                    reason="VERIFICATION_EVIDENCE_RECORDED",
                )
            p.updated_at = time.time()
            p.checkpoints.append(
                CheckpointRecord(
                    stage=p.stage,
                    title="Strategy Coverage Evaluated",
                    evidence_summary=(
                        f"Coverage verdict: {report.verdict}; "
                        f"coverage fraction: {report.confidence_score:.2f}; "
                        f"scope: {report.verification_scope}; "
                        "not deployed-system or scientific validation."
                    ),
                    actor="agent:supra:verifier",
                )
            )
            self._persist_or_restore(project_id, previous)
            return p

    def record_restricted_execution(
        self, project_id: str, result: RestrictedExecutionResult
    ) -> ProjectPosture:
        """Record trusted restricted preflight without claiming process isolation."""
        with self._lock:
            p = self._get_mutable_project(project_id)
            previous = p.model_copy(deep=True)
            expected = (
                candidate_execution_identity(p.selected_candidate)
                if p.selected_candidate is not None
                else None
            )
            identity_matches = bool(
                result.identity_bound
                and expected is not None
                and result.candidate_id == expected["candidate_id"]
                and result.mechanism_version == expected["mechanism_version"]
                and result.claim_id == expected["claim_id"]
                and isinstance(result.protocol_version, str)
                and result.protocol_version.startswith("sha256:")
            )
            result.identity_bound = identity_matches
            p.restricted_execution_results.append(result)

            latest_sandbox = p.secure_sandbox_results[-1] if p.secure_sandbox_results else None
            sandbox_gate = bool(
                latest_sandbox
                and latest_sandbox.passed
                and _sandbox_matches_identity(latest_sandbox, expected)
                and latest_sandbox.isolation_verified
            )
            restricted_gate = bool(result.passed and identity_matches)

            if p.stage is not TaskmasterStage.FAILED:
                if not restricted_gate:
                    p.stage = (
                        TaskmasterStage.STRATIFIED
                        if p.selected_candidate is not None
                        else TaskmasterStage.STRUCTURED
                        if p.decomposition is not None
                        else TaskmasterStage.RECEIVED
                    )
                elif p.stage is not TaskmasterStage.COMPLETED:
                    p.stage = (
                        TaskmasterStage.SECURE_SANDBOX_VERIFIED
                        if sandbox_gate
                        else TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED
                    )

            if p.final_output is not None:
                provenance_raw = p.final_output.get("evidence_provenance")
                provenance = dict(provenance_raw) if isinstance(provenance_raw, dict) else {}
                provenance["restricted_execution_ids"] = [
                    item.execution_id for item in p.restricted_execution_results
                ]
                updates: dict[str, Any] = {
                    "restricted_execution_identity_bound": result.identity_bound,
                    "restricted_execution_status": (
                        "BOUND_PASS"
                        if restricted_gate
                        else "BOUND_FAIL"
                        if result.identity_bound
                        else "UNBOUND"
                    ),
                    "derived_execution_state_revalidated": True,
                    "evidence_provenance": provenance,
                }
                if not restricted_gate:
                    updates.update(
                        {
                            "workflow_status": "BLOCKED",
                            "completion_status": "BLOCKED",
                            "derived_completion_state_revalidated": True,
                        }
                    )
                p.final_output = revise_final_output_payload(
                    p.final_output,
                    updates,
                    reason="RESTRICTED_EXECUTION_EVIDENCE_RECORDED",
                )

            p.updated_at = time.time()
            p.checkpoints.append(
                CheckpointRecord(
                    stage=p.stage,
                    title="Trusted Restricted Execution",
                    evidence_summary=(
                        f"Executed {result.action_type} in {result.duration_ms:.1f}ms. "
                        f"Passed: {result.passed}. Identity bound: {result.identity_bound}. "
                        "Process isolated: False. Scientific validation: False."
                    ),
                    actor="agent:supra:restricted-executor",
                )
            )
            self._persist_or_restore(project_id, previous)
            return p

    def record_secure_sandbox_execution(
        self, project_id: str, result: SecureSandboxResult
    ) -> ProjectPosture:
        """Record an externally isolated sandbox receipt and derive its gate state."""
        with self._lock:
            p = self._get_mutable_project(project_id)
            previous = p.model_copy(deep=True)
            expected = (
                candidate_execution_identity(p.selected_candidate)
                if p.selected_candidate is not None
                else None
            )
            identity_matches = bool(
                result.identity_bound
                and expected is not None
                and result.candidate_id == expected["candidate_id"]
                and result.mechanism_version == expected["mechanism_version"]
                and result.claim_id == expected["claim_id"]
                and isinstance(result.protocol_version, str)
                and result.protocol_version.startswith("sha256:")
                and isinstance(result.image_id, str)
                and result.image_id.startswith("sha256:")
            )
            result.identity_bound = identity_matches
            sandbox_gate = bool(result.passed and identity_matches and result.isolation_verified)
            p.secure_sandbox_results.append(result)

            latest_restricted = (
                p.restricted_execution_results[-1] if p.restricted_execution_results else None
            )
            restricted_gate = bool(
                latest_restricted
                and latest_restricted.passed
                and _restricted_matches_identity(latest_restricted, expected)
            )

            if p.stage is not TaskmasterStage.FAILED:
                if sandbox_gate:
                    if p.stage is not TaskmasterStage.COMPLETED:
                        p.stage = TaskmasterStage.SECURE_SANDBOX_VERIFIED
                else:
                    p.stage = (
                        TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED
                        if restricted_gate
                        else TaskmasterStage.STRATIFIED
                        if p.selected_candidate is not None
                        else TaskmasterStage.STRUCTURED
                        if p.decomposition is not None
                        else TaskmasterStage.RECEIVED
                    )

            if p.final_output is not None:
                provenance_raw = p.final_output.get("evidence_provenance")
                provenance = dict(provenance_raw) if isinstance(provenance_raw, dict) else {}
                provenance["secure_sandbox_execution_ids"] = [
                    item.execution_id for item in p.secure_sandbox_results
                ]
                updates: dict[str, Any] = {
                    "secure_sandbox_identity_bound": result.identity_bound,
                    "secure_sandbox_isolation_verified": result.isolation_verified,
                    "secure_sandbox_execution_scope": result.execution_scope,
                    "candidate_mechanism_executed_in_secure_sandbox": (
                        result.candidate_mechanism_executed
                    ),
                    "secure_sandbox_status": (
                        "IDENTITY_BOUND_ISOLATION_PASS"
                        if sandbox_gate
                        else "IDENTITY_BOUND_ISOLATION_FAIL"
                        if result.identity_bound and result.isolation_verified
                        else "UNVERIFIED_ISOLATION"
                    ),
                    "derived_execution_state_revalidated": True,
                    "evidence_provenance": provenance,
                }
                if not sandbox_gate:
                    updates.update(
                        {
                            "workflow_status": "BLOCKED",
                            "completion_status": "BLOCKED",
                            "derived_completion_state_revalidated": True,
                        }
                    )
                p.final_output = revise_final_output_payload(
                    p.final_output,
                    updates,
                    reason="SECURE_SANDBOX_EVIDENCE_RECORDED",
                )

            p.updated_at = time.time()
            p.checkpoints.append(
                CheckpointRecord(
                    stage=p.stage,
                    title="Secure Sandbox Isolation Smoke",
                    evidence_summary=(
                        f"Backend: {result.backend}. Passed: {result.passed}. "
                        f"Identity bound: {result.identity_bound}. "
                        f"Isolation verified: {result.isolation_verified}. "
                        f"Scope: {result.execution_scope}. Candidate mechanism executed: "
                        f"{result.candidate_mechanism_executed}. Timed out: {result.timed_out}. "
                        "Scientific validation: False."
                    ),
                    actor="agent:supra:secure-sandbox",
                )
            )
            self._persist_or_restore(project_id, previous)
            return p

    def complete_project(self, project_id: str, final_output: dict[str, Any]) -> ProjectPosture:
        """Complete only when verification, preflight, and identity-bound isolation gates pass."""
        with self._lock:
            p = self._get_mutable_project(project_id)
            previous = p.model_copy(deep=True)
            expected = (
                candidate_execution_identity(p.selected_candidate)
                if p.selected_candidate is not None
                else None
            )
            verification_identity_matches = _verification_matches_identity(p.verification, expected)
            verification_status = (
                str(p.verification.verdict)
                if p.verification is not None and verification_identity_matches
                else "NOT_EVALUATED"
            )
            latest_execution = (
                p.restricted_execution_results[-1] if p.restricted_execution_results else None
            )
            latest_sandbox = p.secure_sandbox_results[-1] if p.secure_sandbox_results else None
            execution_identity_matches = _restricted_matches_identity(latest_execution, expected)
            sandbox_identity_matches = _sandbox_matches_identity(latest_sandbox, expected)
            execution_gate = bool(
                latest_execution and latest_execution.passed and execution_identity_matches
            )
            sandbox_gate = bool(
                latest_sandbox
                and latest_sandbox.passed
                and sandbox_identity_matches
                and latest_sandbox.isolation_verified
            )
            execution_status = (
                "BOUND_PASS"
                if execution_gate
                else "BOUND_FAIL"
                if execution_identity_matches
                else "UNBOUND"
                if latest_execution
                else "NOT_RUN"
            )
            sandbox_status = (
                "IDENTITY_BOUND_ISOLATION_PASS"
                if sandbox_gate
                else "IDENTITY_BOUND_ISOLATION_FAIL"
                if latest_sandbox is not None
                and sandbox_identity_matches
                and latest_sandbox.isolation_verified
                else "UNVERIFIED_ISOLATION"
                if latest_sandbox
                else "NOT_RUN"
            )
            verification_gate = verification_identity_matches and verification_status in {
                "PASS",
                "CONDITIONAL_PASS",
            }
            if not verification_gate or not execution_gate or not sandbox_gate:
                p.updated_at = time.time()
                p.checkpoints.append(
                    CheckpointRecord(
                        stage=p.stage,
                        title="Completion Gate Blocked",
                        evidence_summary=(
                            f"Completion blocked. Verification gate: {verification_status}. "
                            f"Restricted preflight gate: {execution_status}. "
                            f"Secure sandbox gate: {sandbox_status}."
                        ),
                        actor="system:completion_gate",
                    )
                )
                self._persist_or_restore(project_id, previous)
                raise CompletionGateError(
                    "Completion requires verification PASS/CONDITIONAL_PASS, "
                    "current BOUND_PASS restricted preflight, and current "
                    "IDENTITY_BOUND_ISOLATION_PASS sandbox isolation smoke."
                )

            payload = dict(final_output)
            payload["restricted_execution_status"] = execution_status
            payload["secure_sandbox_status"] = sandbox_status
            payload["secure_sandbox_identity_bound"] = bool(
                latest_sandbox and latest_sandbox.identity_bound
            )
            payload["secure_sandbox_isolation_verified"] = bool(
                latest_sandbox and latest_sandbox.isolation_verified
            )
            payload["secure_sandbox_execution_scope"] = (
                latest_sandbox.execution_scope if latest_sandbox else "NOT_RUN"
            )
            payload["candidate_mechanism_executed_in_secure_sandbox"] = bool(
                latest_sandbox and latest_sandbox.candidate_mechanism_executed
            )
            for stale_key in (
                "audit_sha256",
                "rejected_audit_sha256",
                "integrity_invalidation_reason",
            ):
                payload.pop(stale_key, None)
            payload["integrity_status"] = "CURRENT"
            payload["audit_sha256"] = final_output_audit_sha256(payload)
            p.final_output = payload
            p.stage = TaskmasterStage.COMPLETED
            p.updated_at = time.time()
            p.checkpoints.append(
                CheckpointRecord(
                    stage=TaskmasterStage.COMPLETED,
                    title="Taskmaster Workflow Complete",
                    evidence_summary=(
                        f"Workflow completed. Verification: {verification_status}. "
                        f"Restricted preflight: {execution_status}. "
                        f"Secure sandbox: {sandbox_status}. "
                        "Scientific validation: NOT_CLAIMED."
                    ),
                    actor="agent:supra:coordinator",
                )
            )
            self._persist_or_restore(project_id, previous)
            return p

    def fail_project(self, project_id: str, error_message: str) -> ProjectPosture:
        """Mark project as FAILED."""
        with self._lock:
            p = self._get_required_project(project_id)
            previous = p.model_copy(deep=True)
            p.error_message = error_message
            p.stage = TaskmasterStage.FAILED
            p.updated_at = time.time()
            p.checkpoints.append(
                CheckpointRecord(
                    stage=TaskmasterStage.FAILED,
                    title="Mission Aborted",
                    evidence_summary=f"Error encountered: {error_message}",
                    actor="system:safety_guard",
                )
            )
            self._persist_or_restore(project_id, previous)
            return p

    def list_projects(self, limit: int = 50) -> list[ProjectPosture]:
        """List recent projects sorted by update time."""
        with self._lock:
            # Sync any disk projects
            for p_file in self.storage_dir.glob("*.json"):
                pid = p_file.stem
                if pid not in self._projects:
                    try:
                        self.get_project(pid)
                    except ValueError:
                        logger.warning(
                            "Ignoring invalid persisted project filename: %s", p_file.name
                        )
            items = list(self._projects.values())
            items.sort(key=lambda x: x.updated_at, reverse=True)
            return items[:limit]

    def _get_required_project(self, project_id: str) -> ProjectPosture:
        p = self.get_project(project_id)
        if not p:
            raise KeyError(f"Project '{project_id}' not found.")
        return p

    def _get_mutable_project(self, project_id: str) -> ProjectPosture:
        """Return project state while keeping FAILED terminal and replay-safe."""
        project = self._get_required_project(project_id)
        if project.stage is TaskmasterStage.FAILED:
            raise ProjectTerminalStateError(
                f"Project '{project_id}' is FAILED; create a new project ID to retry."
            )
        return project

    def _persist_or_restore(
        self,
        project_id: str,
        previous: ProjectPosture | None,
    ) -> None:
        """Persist one mutation or restore the manager's prior in-memory state."""
        try:
            self._persist_project(project_id)
        except Exception:
            if previous is None:
                self._projects.pop(project_id, None)
            else:
                self._projects[project_id] = previous
            raise

    def _persist_project(self, project_id: str) -> None:
        """Persist project atomically after validating its storage identity."""
        project_id = validate_project_id(project_id)
        p = self._projects.get(project_id)
        if not p:
            logger.error(f"Cannot persist non-existent project {project_id}")
            return
        tmp_path: Path | None = None
        try:
            p_file = self.storage_dir / f"{project_id}.json"
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.storage_dir,
                suffix=".tmp",
                delete=False,
            ) as tmp:
                tmp.write(p.model_dump_json(indent=2))
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_path = Path(tmp.name)
            tmp_path.replace(p_file)
        except Exception as exc:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            error_type = type(exc).__name__
            logger.error(
                "Project persistence failed (%s); data-loss risk for project %s",
                error_type,
                project_id,
            )
            raise RuntimeError(
                f"Persistence failed for project {project_id} ({error_type})"
            ) from exc


# Global Singleton Instance
state_manager = ProjectStateManager()

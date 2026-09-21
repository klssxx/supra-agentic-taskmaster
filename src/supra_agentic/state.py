"""Thread-safe file-backed project state manager.

Filesystem storage is classified honestly as local, configured, or instance
ephemeral. A configured path may be durable only when the deployment mounts
a durable external backend there.
"""

from __future__ import annotations

import json
import logging
import os
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
    StrategyCandidate,
    StructuredDecomposition,
    TaskmasterStage,
    VerificationReport,
)

logger = logging.getLogger("supra_agentic.state")


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
            pid = project_id or f"proj-{uuid.uuid4().hex[:8]}"
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
            self._persist_project(pid)
            return posture

    def get_project(self, project_id: str) -> ProjectPosture | None:
        """Retrieve a project state by ID."""
        with self._lock:
            if project_id in self._projects:
                return self._projects[project_id]
            # Try to load from disk
            p_file = self.storage_dir / f"{project_id}.json"
            if p_file.exists():
                try:
                    data = json.loads(p_file.read_text(encoding="utf-8"))
                    posture = ProjectPosture.model_validate(data)
                    self._projects[project_id] = posture
                    return posture
                except Exception as exc:
                    logger.error(f"Failed to load project {project_id} from disk: {exc}")
            return None

    def update_decomposition(
        self, project_id: str, decomp: StructuredDecomposition
    ) -> ProjectPosture:
        """Store decomposition and advance stage to STRUCTURED."""
        with self._lock:
            p = self._get_required_project(project_id)
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
            self._persist_project(project_id)
            return p

    def add_candidates(
        self, project_id: str, candidates: list[StrategyCandidate], select_best: bool = True
    ) -> ProjectPosture:
        """Store strategy candidates and advance stage to STRATIFIED."""
        with self._lock:
            p = self._get_required_project(project_id)
            p.candidates = candidates
            if select_best and candidates:
                # Select candidate with highest combined feasibility + divergence score
                best = max(
                    candidates, key=lambda c: c.feasibility_score * 0.6 + c.divergence_score * 0.4
                )
                best.is_selected = True
                p.selected_candidate = best
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
            self._persist_project(project_id)
            return p

    def record_verification(self, project_id: str, report: VerificationReport) -> ProjectPosture:
        """Store verification report."""
        with self._lock:
            p = self._get_required_project(project_id)
            p.verification = report
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
            self._persist_project(project_id)
            return p

    def record_restricted_execution(
        self, project_id: str, result: RestrictedExecutionResult
    ) -> ProjectPosture:
        """Record trusted restricted execution without claiming process isolation."""
        with self._lock:
            p = self._get_required_project(project_id)
            p.restricted_execution_results.append(result)
            if result.passed and result.identity_bound:
                p.stage = TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED
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
            self._persist_project(project_id)
            return p

    def complete_project(self, project_id: str, final_output: dict[str, Any]) -> ProjectPosture:
        """Mark workflow completion without implying verification or scientific proof."""
        with self._lock:
            p = self._get_required_project(project_id)
            p.final_output = final_output
            p.stage = TaskmasterStage.COMPLETED
            p.updated_at = time.time()
            verification_status = (
                str(p.verification.verdict) if p.verification else "NOT_EVALUATED"
            )
            latest_execution = (
                p.restricted_execution_results[-1]
                if p.restricted_execution_results
                else None
            )
            execution_status = (
                "BOUND_PASS"
                if latest_execution and latest_execution.passed and latest_execution.identity_bound
                else "BOUND_FAIL"
                if latest_execution and latest_execution.identity_bound
                else "UNBOUND"
                if latest_execution
                else "NOT_RUN"
            )
            p.checkpoints.append(
                CheckpointRecord(
                    stage=TaskmasterStage.COMPLETED,
                    title="Taskmaster Workflow Complete",
                    evidence_summary=(
                        f"Workflow completed. Verification status: {verification_status}. "
                        f"Restricted execution status: {execution_status}. "
                        "Scientific validation: NOT_CLAIMED."
                    ),
                    actor="agent:supra:coordinator",
                )
            )
            self._persist_project(project_id)
            return p

    def fail_project(self, project_id: str, error_message: str) -> ProjectPosture:
        """Mark project as FAILED."""
        with self._lock:
            p = self._get_required_project(project_id)
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
            self._persist_project(project_id)
            return p

    def list_projects(self, limit: int = 50) -> list[ProjectPosture]:
        """List recent projects sorted by update time."""
        with self._lock:
            # Sync any disk projects
            for p_file in self.storage_dir.glob("*.json"):
                pid = p_file.stem
                if pid not in self._projects:
                    self.get_project(pid)
            items = list(self._projects.values())
            items.sort(key=lambda x: x.updated_at, reverse=True)
            return items[:limit]

    def _get_required_project(self, project_id: str) -> ProjectPosture:
        p = self.get_project(project_id)
        if not p:
            raise KeyError(f"Project '{project_id}' not found.")
        return p

    def _persist_project(self, project_id: str) -> None:
        """Persist project to disk with proper error handling (B-6 fix)."""
        p = self._projects.get(project_id)
        if not p:
            logger.error(f"Cannot persist non-existent project {project_id}")
            return
        try:
            p_file = self.storage_dir / f"{project_id}.json"
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.storage_dir, suffix=".tmp", delete=False
            ) as tmp:
                tmp.write(p.model_dump_json(indent=2))
                tmp_path = Path(tmp.name)
            tmp_path.replace(p_file)
        except Exception as exc:
            # B-6 fix: Don't silently fail - log with full traceback and re-raise
            logger.exception(f"CRITICAL: Failed to persist project {project_id} - data loss risk!")
            raise RuntimeError(f"Persistence failed for project {project_id}: {exc}") from exc


# Global Singleton Instance
state_manager = ProjectStateManager()

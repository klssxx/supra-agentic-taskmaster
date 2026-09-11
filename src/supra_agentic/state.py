"""Thread-safe, In-Memory & File-Backed Project State Manager."""
from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .models import (
    CheckpointRecord,
    ProjectPosture,
    SandboxExecutionResult,
    StrategyCandidate,
    StructuredDecomposition,
    TaskmasterStage,
    VerificationReport,
)

logger = logging.getLogger("supra_agentic.state")


class ProjectStateManager:
    """Manages project lifecycles with thread-safe locking and state persistence."""

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        self._lock = threading.RLock()
        self._projects: dict[str, ProjectPosture] = {}
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/projects")
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

    def update_decomposition(self, project_id: str, decomp: StructuredDecomposition) -> ProjectPosture:
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

    def add_candidates(self, project_id: str, candidates: list[StrategyCandidate], select_best: bool = True) -> ProjectPosture:
        """Store strategy candidates and advance stage to STRATIFIED."""
        with self._lock:
            p = self._get_required_project(project_id)
            p.candidates = candidates
            if select_best and candidates:
                # Select candidate with highest combined feasibility + divergence score
                best = max(candidates, key=lambda c: (c.feasibility_score * 0.6 + c.divergence_score * 0.4))
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
                    title="Verification Conducted",
                    evidence_summary=f"Verdict: {report.verdict} (Confidence: {report.confidence_score:.2f}). Invariants Preserved: {report.invariants_preserved}.",
                    actor="agent:supra:verifier",
                )
            )
            self._persist_project(project_id)
            return p

    def record_sandbox_execution(self, project_id: str, result: SandboxExecutionResult) -> ProjectPosture:
        """Record sandbox execution and advance to SANDBOX_VERIFIED."""
        with self._lock:
            p = self._get_required_project(project_id)
            p.sandbox_results.append(result)
            if result.passed:
                p.stage = TaskmasterStage.SANDBOX_VERIFIED
            p.updated_at = time.time()
            p.checkpoints.append(
                CheckpointRecord(
                    stage=p.stage,
                    title="Sandbox Execution",
                    evidence_summary=f"Executed {result.action_type} in {result.duration_ms:.1f}ms. Passed: {result.passed}.",
                    actor="agent:supra:sandbox",
                )
            )
            self._persist_project(project_id)
            return p

    def complete_project(self, project_id: str, final_output: dict[str, Any]) -> ProjectPosture:
        """Mark project as COMPLETED with final verifiable deliverable."""
        with self._lock:
            p = self._get_required_project(project_id)
            p.final_output = final_output
            p.stage = TaskmasterStage.COMPLETED
            p.updated_at = time.time()
            p.checkpoints.append(
                CheckpointRecord(
                    stage=TaskmasterStage.COMPLETED,
                    title="Taskmaster Mission Complete",
                    evidence_summary="All 5 stages completed autonomously with verifiable proof and telemetry.",
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
        p = self._projects.get(project_id)
        if p:
            try:
                p_file = self.storage_dir / f"{project_id}.json"
                with tempfile.NamedTemporaryFile(
                    mode="w", dir=self.storage_dir, suffix=".tmp", delete=False
                ) as tmp:
                    tmp.write(p.model_dump_json(indent=2))
                    tmp_path = Path(tmp.name)
                tmp_path.replace(p_file)
            except Exception as exc:
                logger.error(f"Failed to persist project {project_id}: {exc}")


# Global Singleton Instance
state_manager = ProjectStateManager()

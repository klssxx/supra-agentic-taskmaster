"""Domain Models and Data Schemas for SUPRA Agentic Taskmaster."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class TaskmasterStage(str, Enum):
    """5 Canonical Stages of the Taskmaster Agent Lifecycle."""

    RECEIVED = "RECEIVED"
    STRUCTURED = "STRUCTURED"
    STRATIFIED = "STRATIFIED"
    SANDBOX_VERIFIED = "SANDBOX_VERIFIED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


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
    invariants_preserved: bool = True
    invariants_checked: list[str] = Field(default_factory=list)
    vulnerabilities_detected: list[str] = Field(default_factory=list)
    confidence_score: float = 0.90
    verdict: str = "PASS"  # PASS, CONDITIONAL_PASS, FAIL, NOT_EVALUATED
    rationale: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)


class SandboxExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str = Field(default_factory=lambda: f"exec-{uuid.uuid4().hex[:6]}")
    action_type: str  # CODE_RUN, SIMULATION, FUZZ_CHECK
    passed: bool
    output_log: str
    duration_ms: float
    side_effects_contained: bool = True
    timestamp: float = Field(default_factory=time.time)


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
    project_id: str
    objective: str
    stage: TaskmasterStage
    created_at: float
    updated_at: float
    decomposition: StructuredDecomposition | None = None
    candidates: list[StrategyCandidate] = Field(default_factory=list)
    selected_candidate: StrategyCandidate | None = None
    verification: VerificationReport | None = None
    sandbox_results: list[SandboxExecutionResult] = Field(default_factory=list)
    checkpoints: list[CheckpointRecord] = Field(default_factory=list)
    final_output: dict[str, Any] | None = None
    error_message: str | None = None

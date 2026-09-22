"""Behavioral ASTRA sentinels for SUPRA product paths."""

from __future__ import annotations

import tempfile

import pytest
import supra_agentic.runner as runner_module
from pydantic import ValidationError
from supra_agentic.models import ProjectPosture, TaskmasterStage, VerificationReport
from supra_agentic.runner import TaskmasterRunner
from supra_agentic.state import CompletionGateError, state_manager
from supra_agentic.tools import (
    decompose_objective,
    record_checkpoint,
    restricted_python_executor,
    synthesize_strategy,
)


def _fresh_project(objective: str = "claim"):
    tmp = tempfile.TemporaryDirectory()
    state_manager.storage_dir = type(state_manager.storage_dir)(tmp.name)
    project = state_manager.create_project(objective)
    return tmp, project


def _selected_project():
    tmp, project = _fresh_project("preserve integrity with audit")
    decompose_objective(
        project.project_id,
        "preserve integrity with audit",
        invariants=["audit trail is preserved"],
    )
    synthesize_strategy(project.project_id, pathways_count=2, allow_disruptive=False)
    posture = state_manager.get_project(project.project_id)
    assert posture and posture.selected_candidate
    return tmp, posture


def _prepare_completion_fixture(posture: ProjectPosture) -> None:
    """Install explicit test-only completion evidence; never used by product code."""
    selected = posture.selected_candidate
    assert selected is not None
    state_manager.record_verification(
        posture.project_id,
        VerificationReport(
            candidate_id=selected.candidate_id,
            invariants_preserved=True,
            invariants_checked=["test-fixture completion invariant"],
            vulnerabilities_detected=[],
            confidence_score=1.0,
            verdict="PASS",
            rationale="TEST_FIXTURE_ONLY: explicit passing completion evidence.",
            evidence=[{"status": "PASS", "scope": "TEST_FIXTURE_ONLY"}],
        ),
    )
    result = restricted_python_executor(posture.project_id)["restricted_execution_result"]
    assert result["passed"] is True
    assert result["identity_bound"] is True


def test_astra_006_verdict_vocabulary_is_closed_and_score_semantics_are_scoped():
    with pytest.raises(ValidationError):
        VerificationReport(candidate_id="c", verdict="VERIFIED_BY_MAGIC")

    report = VerificationReport(candidate_id="c")
    assert report.verdict == "NOT_EVALUATED"
    assert report.verification_scope == "TEXTUAL_STRATEGY_COVERAGE"
    assert report.measurement_kind == "HEURISTIC_COVERAGE"
    assert "FRACTION" in report.confidence_semantics


def test_astra_017_unbound_restricted_execution_cannot_advance_stage():
    tmp, project = _fresh_project()
    try:
        result = restricted_python_executor(project.project_id)
        assert result["restricted_execution_result"]["passed"] is True
        assert result["restricted_execution_result"]["identity_bound"] is False
        posture = state_manager.get_project(project.project_id)
        assert posture is not None
        assert posture.stage is TaskmasterStage.RECEIVED
    finally:
        tmp.cleanup()


def test_astra_017_product_execution_derives_binding_from_persisted_candidate():
    tmp, posture = _selected_project()
    try:
        selected = posture.selected_candidate
        assert selected is not None
        result = restricted_python_executor(posture.project_id)
        execution = result["restricted_execution_result"]
        assert execution["passed"] is True
        assert execution["identity_bound"] is True
        assert execution["execution_semantics_version"] == 2
        assert execution["candidate_id"] == selected.candidate_id
        assert execution["claim_id"].startswith("claim-")
        assert execution["mechanism_version"].startswith("sha256:")
        assert execution["protocol_version"].startswith("sha256:")
        assert result["stage"] == "RESTRICTED_EXECUTION_VERIFIED"
    finally:
        tmp.cleanup()


def test_astra_017_caller_identity_assertion_cannot_override_persisted_candidate():
    tmp, posture = _selected_project()
    try:
        with pytest.raises(ValueError, match="candidate_id"):
            restricted_python_executor(posture.project_id, candidate_id="forged-candidate")
        current = state_manager.get_project(posture.project_id)
        assert current is not None
        assert current.restricted_execution_results == []
    finally:
        tmp.cleanup()


def test_astra_020_not_evaluated_cannot_satisfy_completion_gate():
    tmp, project = _fresh_project()
    try:
        with pytest.raises(CompletionGateError):
            record_checkpoint(project.project_id, "title", "summary")
        current = state_manager.get_project(project.project_id)
        assert current is not None
        assert current.verification is None
        assert current.stage is not TaskmasterStage.COMPLETED
        assert current.final_output is None
        assert current.checkpoints[-1].title == "Completion Gate Blocked"
    finally:
        tmp.cleanup()


def test_astra_024_026_checkpoint_declares_incomplete_dependency_and_budget_closure():
    tmp, posture = _selected_project()
    try:
        _prepare_completion_fixture(posture)
        final = record_checkpoint(posture.project_id, "title", "summary")["final_deliverable"]
        deps = final["reproducibility_dependencies"]
        accounting = final["opportunity_accounting"]
        assert deps["closure_complete"] is False
        assert "code_version" in deps["known_unclosed_dependencies"]
        assert accounting["candidate_opportunities"] == len(
            state_manager.get_project(posture.project_id).candidates
        )
        assert accounting["restricted_execution_attempts"] == 1
        assert accounting["provider_generation_calls"] is None
        assert accounting["budget_complete"] is False
    finally:
        tmp.cleanup()


def test_astra_028_strong_scientific_evaluator_claims_remain_disabled():
    tmp, project = _selected_project()
    try:
        _prepare_completion_fixture(project)
        final = record_checkpoint(project.project_id, "title", "summary")["final_deliverable"]
        controls = final["evaluator_controls"]
        assert controls == {
            "blinding": False,
            "positive_controls": False,
            "negative_controls": False,
            "disagreement_analysis": False,
            "strong_scientific_claims_supported": False,
        }
    finally:
        tmp.cleanup()


def test_astra_033_failed_restricted_attempt_is_preserved_after_later_success():
    tmp, posture = _selected_project()
    try:
        failed = restricted_python_executor(
            posture.project_id,
            code_snippet="raise RuntimeError('sentinel failure')",
            trusted_internal=True,
        )["restricted_execution_result"]
        passed = restricted_python_executor(posture.project_id)["restricted_execution_result"]
        current = state_manager.get_project(posture.project_id)
        assert current is not None
        assert failed["passed"] is False
        assert failed["error_type"] == "RuntimeError"
        assert passed["passed"] is True
        assert [item.passed for item in current.restricted_execution_results] == [False, True]
        assert "sentinel failure" not in current.restricted_execution_results[0].output_log
    finally:
        tmp.cleanup()


def test_astra_b03_legacy_verified_stage_is_downgraded_without_bound_execution():
    raw = {
        "project_id": "legacy-project",
        "objective": "legacy",
        "stage": "SANDBOX_VERIFIED",
        "created_at": 1.0,
        "updated_at": 2.0,
        "sandbox_results": [
            {
                "action_type": "legacy",
                "passed": True,
                "output_log": "legacy-pass",
                "duration_ms": 1.0,
            }
        ],
        "checkpoints": [],
    }
    posture = ProjectPosture.model_validate(raw)
    assert posture.stage is TaskmasterStage.STRATIFIED
    assert posture.restricted_execution_results
    assert posture.restricted_execution_results[0].identity_bound is False
    assert posture.checkpoints[-1].title == "Legacy execution accreditation invalidated"


def test_astra_b03_current_verified_stage_is_downgraded_if_binding_was_not_persisted():
    raw = {
        "project_id": "legacy-current-project",
        "objective": "legacy-current",
        "stage": "RESTRICTED_EXECUTION_VERIFIED",
        "created_at": 1.0,
        "updated_at": 2.0,
        "restricted_execution_results": [
            {
                "action_type": "legacy-current",
                "passed": True,
                "output_log": "legacy-pass",
                "duration_ms": 1.0,
            }
        ],
        "checkpoints": [],
    }
    posture = ProjectPosture.model_validate(raw)
    assert posture.stage is TaskmasterStage.STRATIFIED
    assert posture.restricted_execution_results[0].identity_bound is False


def test_astra_033_restricted_exception_message_is_redacted(tmp_path):
    state_manager.storage_dir = type(state_manager.storage_dir)(tmp_path)
    p = state_manager.create_project("redaction")
    decompose_objective(p.project_id, "redaction")
    synthesize_strategy(p.project_id, pathways_count=1, allow_disruptive=False)
    result = restricted_python_executor(
        p.project_id,
        code_snippet="raise RuntimeError('SENTINEL_SECRET_DO_NOT_LEAK')",
        trusted_internal=True,
    )["restricted_execution_result"]
    assert result["passed"] is False
    assert result["error_type"] == "RuntimeError"
    assert "SENTINEL_SECRET_DO_NOT_LEAK" not in result["output_log"]


def test_astra_017_runner_cannot_complete_without_bound_passing_execution(monkeypatch, tmp_path):
    state_manager.storage_dir = type(state_manager.storage_dir)(tmp_path)

    def _failed_execution(project_id: str, fuzz_iterations: int = 5):
        return {
            "status": "success",
            "project_id": project_id,
            "stage": "STRATIFIED",
            "restricted_execution_result": {
                "passed": False,
                "identity_bound": False,
                "output_log": "SENTINEL_INTERNAL_DETAIL",
            },
        }

    monkeypatch.setattr(runner_module, "restricted_python_executor", _failed_execution)
    runner = TaskmasterRunner()
    posture = runner.run_golden_path(
        "bounded workflow",
        max_retries=0,
        use_model=False,
    )
    assert posture.stage is TaskmasterStage.FAILED
    assert posture.final_output is None
    assert posture.error_message == "Taskmaster execution failed (RuntimeError)"
    assert "SENTINEL_INTERNAL_DETAIL" not in posture.error_message


def test_astra_b03_ids_alone_cannot_reactivate_pre_versioned_execution():
    raw = {
        "project_id": "legacy-complete-ids",
        "objective": "legacy-complete-ids",
        "stage": "RESTRICTED_EXECUTION_VERIFIED",
        "created_at": 1.0,
        "updated_at": 2.0,
        "restricted_execution_results": [
            {
                "execution_id": "exec-old",
                "candidate_id": "cand-old",
                "mechanism_version": "sha256:old",
                "claim_id": "claim-old",
                "protocol_version": "sha256:old-protocol",
                "action_type": "legacy",
                "passed": True,
                "output_log": "legacy-pass",
                "duration_ms": 1.0,
            }
        ],
        "checkpoints": [],
    }
    posture = ProjectPosture.model_validate(raw)
    assert posture.stage is TaskmasterStage.STRATIFIED
    assert posture.restricted_execution_results[0].identity_bound is False
    assert posture.restricted_execution_results[0].execution_semantics_version is None


def test_astra_b03_current_semantics_with_forged_candidate_identity_is_downgraded():
    raw = {
        "project_id": "forged-current",
        "objective": "forged-current",
        "stage": "RESTRICTED_EXECUTION_VERIFIED",
        "created_at": 1.0,
        "updated_at": 2.0,
        "selected_candidate": {
            "candidate_id": "cand-real",
            "pathway_name": "real-path",
            "paradigm_type": "CONSERVATIVE",
            "hypothesis": "real hypothesis",
            "action_plan": ["step"],
            "is_selected": True,
        },
        "restricted_execution_results": [
            {
                "execution_id": "exec-forged",
                "execution_semantics_version": 2,
                "candidate_id": "cand-forged",
                "mechanism_version": "sha256:" + "0" * 64,
                "claim_id": "claim-forged",
                "protocol_version": "sha256:" + "1" * 64,
                "action_type": "legacy-forged",
                "passed": True,
                "output_log": "forged",
                "duration_ms": 1.0,
            }
        ],
        "checkpoints": [],
    }
    posture = ProjectPosture.model_validate(raw)
    assert posture.stage is TaskmasterStage.STRATIFIED
    assert posture.restricted_execution_results[0].identity_bound is False
    assert posture.checkpoints[-1].title == "Persisted execution accreditation invalidated"


def test_astra_b03_completed_workflow_revalidates_and_revokes_stale_completion():
    raw = {
        "project_id": "completed-stale-derived",
        "objective": "completed-stale-derived",
        "stage": "COMPLETED",
        "created_at": 1.0,
        "updated_at": 2.0,
        "selected_candidate": {
            "candidate_id": "cand-real",
            "pathway_name": "real-path",
            "paradigm_type": "CONSERVATIVE",
            "hypothesis": "real hypothesis",
            "action_plan": ["step"],
            "is_selected": True,
        },
        "restricted_execution_results": [
            {
                "execution_id": "exec-forged",
                "execution_semantics_version": 2,
                "candidate_id": "cand-forged",
                "mechanism_version": "sha256:" + "0" * 64,
                "claim_id": "claim-forged",
                "protocol_version": "sha256:" + "1" * 64,
                "action_type": "legacy-forged",
                "passed": True,
                "output_log": "forged",
                "duration_ms": 1.0,
            }
        ],
        "final_output": {
            "workflow_status": "COMPLETED",
            "restricted_execution_identity_bound": True,
            "restricted_execution_status": "BOUND_PASS",
            "scientific_status": "NOT_VALIDATED",
        },
        "checkpoints": [],
    }
    posture = ProjectPosture.model_validate(raw)
    assert posture.stage is TaskmasterStage.STRATIFIED
    assert posture.restricted_execution_results[0].identity_bound is False
    assert posture.final_output is not None
    assert posture.final_output["workflow_status"] == "BLOCKED"
    assert posture.final_output["completion_status"] == "BLOCKED"
    assert posture.final_output["restricted_execution_identity_bound"] is False
    assert posture.final_output["restricted_execution_status"] == "UNBOUND"
    assert posture.final_output["derived_execution_state_revalidated"] is True
    assert posture.final_output["derived_completion_state_revalidated"] is True
    assert posture.checkpoints[-1].title == "Persisted completion invalidated"

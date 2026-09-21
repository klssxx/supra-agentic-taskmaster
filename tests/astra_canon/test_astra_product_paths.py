"""Behavioral ASTRA sentinels for SUPRA product paths."""

from __future__ import annotations

import tempfile

import pytest
from pydantic import ValidationError

from supra_agentic.models import TaskmasterStage, VerificationReport
from supra_agentic.state import state_manager
from supra_agentic.tools import (
    decompose_objective,
    record_checkpoint,
    restricted_python_executor,
    synthesize_strategy,
    verify_solution,
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


def test_astra_020_not_evaluated_can_complete_workflow_without_becoming_validation():
    tmp, project = _fresh_project()
    try:
        result = record_checkpoint(project.project_id, "title", "summary")
        final = result["final_deliverable"]
        assert result["stage"] == "COMPLETED"
        assert final["workflow_status"] == "COMPLETED"
        assert final["verification_verdict"] == "NOT_EVALUATED"
        assert final["h0_evaluation_status"] == "NOT_EVALUATED"
        assert final["scientific_status"] == "NOT_VALIDATED"
        assert final["independent_confirmation_status"] == "NOT_ESTABLISHED"
        assert final["learning_update_status"] == "NOT_APPLICABLE"
        assert final["integrity_semantics"] == "SHA256_OF_SERIALIZED_PAYLOAD_NOT_TRUTH"
    finally:
        tmp.cleanup()


def test_astra_024_026_checkpoint_declares_incomplete_dependency_and_budget_closure():
    tmp, posture = _selected_project()
    try:
        verify_solution(posture.project_id)
        restricted_python_executor(posture.project_id)
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
    tmp, project = _fresh_project()
    try:
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
        assert passed["passed"] is True
        assert [item.passed for item in current.restricted_execution_results] == [False, True]
        assert "sentinel failure" in current.restricted_execution_results[0].output_log
    finally:
        tmp.cleanup()

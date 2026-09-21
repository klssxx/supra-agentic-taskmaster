"""SUPRA sentinels for ASTRA-001/003/017/018/019/020/026/028/031."""

import tempfile

import pytest
from supra_agentic.dossier import generate_svg_architecture
from supra_agentic.models import RestrictedExecutionResult, TaskmasterStage
from supra_agentic.state import state_manager
from supra_agentic.tools import (
    decompose_objective,
    record_checkpoint,
    restricted_python_executor,
    synthesize_strategy,
    verify_solution,
)


def test_astra_017_restricted_execution_model_cannot_claim_scientific_validation():
    with pytest.raises(ValueError, match="scientific validation"):
        RestrictedExecutionResult(
            action_type="x", passed=True, output_log="", duration_ms=1, scientific_validation=True
        )


def test_astra_017_execution_identity_and_scope_are_explicit():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)
        p = state_manager.create_project("claim")
        result = restricted_python_executor(
            p.project_id,
            candidate_id="candidate-A",
            mechanism_version="m-v1",
            claim_id="claim-A",
            protocol_version="restricted-v1",
        )["restricted_execution_result"]
        assert result["candidate_id"] == "candidate-A"
        assert result["mechanism_version"] == "m-v1"
        assert result["claim_id"] == "claim-A"
        assert result["protocol_version"] == "restricted-v1"
        assert result["execution_id"]
        assert result["result_scope"] == "RESTRICTED_EXECUTION_ONLY"
        assert result["scientific_validation"] is False
        assert result["identity_bound"] is False
        assert state_manager.get_project(p.project_id).stage == TaskmasterStage.RECEIVED


def test_astra_001_checkpoint_without_verification_is_not_evaluated():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)
        p = state_manager.create_project("claim")
        final = record_checkpoint(p.project_id, "title", "summary")["final_deliverable"]
        assert final["verification_verdict"] == "NOT_EVALUATED"


def test_astra_017_svg_without_verification_never_defaults_to_pass():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)
        p = state_manager.create_project("claim")
        assert "NOT_EVALUATED" in generate_svg_architecture(p)


def test_astra_017_only_identity_bound_explicit_internal_check_advances_stage():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)
        p = state_manager.create_project("claim")
        decompose_objective(p.project_id, p.objective)
        synthesize_strategy(p.project_id)
        posture = state_manager.get_project(p.project_id)
        assert posture and posture.selected_candidate
        result = restricted_python_executor(
            p.project_id,
            candidate_id=posture.selected_candidate.candidate_id,
            code_snippet="print('candidate-bound-check')",
            trusted_internal=True,
            mechanism_version="m-v1",
            claim_id="claim-A",
            protocol_version="restricted-v1",
        )["restricted_execution_result"]
        assert result["identity_bound"] is True
        assert state_manager.get_project(p.project_id).stage == TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED


def test_astra_006_verification_score_declares_heuristic_scope():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)
        p = state_manager.create_project("claim")
        decompose_objective(p.project_id, p.objective)
        synthesize_strategy(p.project_id)
        report = verify_solution(p.project_id)["report"]
        assert report["verification_scope"] == "STRATEGY_TEXT_COVERAGE_ONLY"
        assert report["confidence_semantics"] == "fraction_of_declared_invariants_with_textual_coverage"


def test_astra_017_completed_checkpoint_is_terminal_state_not_proof():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)
        p = state_manager.create_project("claim")
        record_checkpoint(p.project_id, "title", "summary")
        posture = state_manager.get_project(p.project_id)
        assert posture and posture.stage == TaskmasterStage.COMPLETED
        summary = posture.checkpoints[-1].evidence_summary.lower()
        assert "does not imply scientific validation" in summary
        assert "verifiable proof" not in summary

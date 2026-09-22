"""Focused SUPRA sentinels for ASTRA epistemic boundaries."""

import tempfile

import pytest
from supra_agentic.dossier import generate_svg_architecture
from supra_agentic.models import RestrictedExecutionResult
from supra_agentic.state import CompletionGateError, state_manager
from supra_agentic.tools import (
    decompose_objective,
    record_checkpoint,
    restricted_python_executor,
    synthesize_strategy,
)


def test_astra_017_restricted_execution_model_cannot_claim_scientific_validation():
    with pytest.raises(ValueError, match="scientific validation"):
        RestrictedExecutionResult(
            action_type="x",
            passed=True,
            output_log="",
            duration_ms=1,
            scientific_validation=True,
        )


def test_astra_017_execution_identity_is_derived_from_selected_candidate():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)
        p = state_manager.create_project("claim")
        decompose_objective(p.project_id, "claim")
        synthesize_strategy(p.project_id, pathways_count=2, allow_disruptive=False)
        selected = state_manager.get_project(p.project_id).selected_candidate
        assert selected is not None

        result = restricted_python_executor(p.project_id)["restricted_execution_result"]
        assert result["candidate_id"] == selected.candidate_id
        assert result["mechanism_version"].startswith("sha256:")
        assert result["claim_id"].startswith("claim-")
        assert result["protocol_version"].startswith("sha256:")
        assert result["execution_id"]
        assert result["identity_bound"] is True
        assert result["result_scope"] == "RESTRICTED_EXECUTION_ONLY"
        assert result["scientific_validation"] is False


def test_astra_001_checkpoint_without_verification_is_blocked_not_evaluated():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)
        p = state_manager.create_project("claim")
        with pytest.raises(CompletionGateError):
            record_checkpoint(p.project_id, "title", "summary")
        current = state_manager.get_project(p.project_id)
        assert current is not None
        assert current.verification is None
        assert current.stage.value != "COMPLETED"
        assert current.final_output is None
        assert current.checkpoints[-1].title == "Completion Gate Blocked"


def test_astra_017_svg_without_verification_never_defaults_to_pass():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)
        p = state_manager.create_project("claim")
        svg = generate_svg_architecture(p)
        assert "NOT_EVALUATED" in svg
        assert "PASS" not in svg

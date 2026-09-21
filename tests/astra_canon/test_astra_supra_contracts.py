"""SUPRA sentinels for ASTRA-001/003/017/018/019/020/026/028/031."""

import tempfile

import pytest
from supra_agentic.dossier import generate_svg_architecture
from supra_agentic.models import RestrictedExecutionResult
from supra_agentic.state import state_manager
from supra_agentic.tools import record_checkpoint, restricted_python_executor


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

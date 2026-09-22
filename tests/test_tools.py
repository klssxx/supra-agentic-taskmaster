"""Tests for provider-neutral SUPRA tools."""

import tempfile

import pytest
import supra_agentic.tools as tools_module
from supra_agentic.models import (
    SECURE_SANDBOX_SEMANTICS_VERSION,
    SecureSandboxResult,
    TaskmasterStage,
)
from supra_agentic.state import CompletionGateError, state_manager
from supra_agentic.tools import (
    SUPRA_TOOLS,
    decompose_objective,
    record_checkpoint,
    restricted_python_executor,
    secure_sandbox_executor,
    synthesize_strategy,
    verify_solution,
)


def test_toolset_manifest():
    assert len(SUPRA_TOOLS) == 6
    tool_names = [t.__name__ for t in SUPRA_TOOLS]
    assert "decompose_objective" in tool_names
    assert "synthesize_strategy" in tool_names
    assert "verify_solution" in tool_names
    assert "restricted_python_executor" in tool_names
    assert "secure_sandbox_executor" in tool_names
    assert "record_checkpoint" in tool_names


def test_full_tool_cycle_execution(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Override state manager storage for isolation
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)

        p = state_manager.create_project(
            objective="Automate multi-region database failover with zero data loss"
        )
        pid = p.project_id

        # 1. Decompose
        r1 = decompose_objective(pid, objective=p.objective, domain="cloud_infrastructure")
        assert r1["status"] == "success"
        assert r1["stage"] == TaskmasterStage.STRUCTURED.value
        assert len(r1["decomposition"]["subtasks"]) == 4

        # 2. Synthesize
        r2 = synthesize_strategy(pid, pathways_count=3, allow_disruptive=True)
        assert r2["status"] == "success"
        assert r2["stage"] == TaskmasterStage.STRATIFIED.value
        assert r2["candidates_count"] == 3
        assert r2["selected_candidate"] is not None

        # 3. Verify (honest contract: verdict derives from evidence executed on invariants,
        # never from preset scores)
        r3 = verify_solution(pid)
        assert r3["status"] == "success"
        report = r3["report"]
        # confidence is fraction of invariants with PASS evidence in [0,1]
        assert 0.0 <= report["confidence_score"] <= 1.0
        # verdict is one of the honest states
        assert report["verdict"] in {"PASS", "CONDITIONAL_PASS", "FAIL", "NOT_EVALUATED"}
        # evidence per invariant is recorded and tied to candidate
        assert isinstance(report["evidence"], list)
        assert len(report["evidence"]) == len(report["invariants_checked"])

        # 4. Trusted restricted execution
        r4 = restricted_python_executor(pid)
        assert r4["status"] == "success"
        assert r4["stage"] == TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED.value
        assert r4["restricted_execution_result"]["passed"] is True

        def _fake_sandbox(code: str, *, identity: dict[str, str], config=None):
            assert "SUPRA_SECURE_SANDBOX_OK" in code
            return SecureSandboxResult(
                execution_semantics_version=SECURE_SANDBOX_SEMANTICS_VERSION,
                candidate_id=identity["candidate_id"],
                mechanism_version=identity["mechanism_version"],
                claim_id=identity["claim_id"],
                protocol_version="sha256:" + "2" * 64,
                image="python:test",
                image_id="sha256:" + "3" * 64,
                passed=True,
                observed_result="PASS",
                exit_code=0,
                output_log="SUPRA_SECURE_SANDBOX_OK",
                duration_ms=2.0,
                network_isolated=True,
                read_only_root=True,
                capabilities_dropped=True,
                no_new_privileges=True,
                non_root_user=True,
                resource_limits_applied=True,
            )

        monkeypatch.setattr(tools_module, "run_python_in_secure_docker", _fake_sandbox)
        r5 = secure_sandbox_executor(pid)
        assert r5["status"] == "success"
        assert r5["stage"] == TaskmasterStage.SECURE_SANDBOX_VERIFIED.value
        assert r5["secure_sandbox_status"] == "ISOLATED_BOUND_PASS"

        # 6. Checkpoint / Final Deliverable. Completion is a real three-gate contract.
        if report["verdict"] in {"PASS", "CONDITIONAL_PASS"}:
            r6 = record_checkpoint(
                pid,
                deliverable_title="Multi-Region Zero-Loss Failover Plan",
                summary="Autonomous plan synthesized and verified.",
            )
            assert r6["status"] == "success"
            assert r6["stage"] == TaskmasterStage.COMPLETED.value
            assert "audit_sha256" in r6["final_deliverable"]
            assert len(r6["final_deliverable"]["audit_sha256"]) == 64
            assert r6["final_deliverable"]["secure_sandbox_status"] == "ISOLATED_BOUND_PASS"
        else:
            with pytest.raises(CompletionGateError):
                record_checkpoint(
                    pid,
                    deliverable_title="Multi-Region Zero-Loss Failover Plan",
                    summary="Autonomous plan reached a blocked completion gate.",
                )
            current = state_manager.get_project(pid)
            assert current is not None
            assert current.stage == TaskmasterStage.SECURE_SANDBOX_VERIFIED
            assert current.final_output is None


def test_secure_sandbox_unavailable_is_recorded_as_blocked(
    monkeypatch: pytest.MonkeyPatch,
):
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)
        p = state_manager.create_project(objective="sandbox unavailable")
        decompose_objective(p.project_id, p.objective)
        synthesize_strategy(p.project_id, pathways_count=1, allow_disruptive=False)
        restricted_python_executor(p.project_id)

        def _missing_backend(*_args, **_kwargs):
            from supra_agentic.sandbox import SandboxUnavailableError

            raise SandboxUnavailableError("no docker")

        monkeypatch.setattr(tools_module, "run_python_in_secure_docker", _missing_backend)
        result = secure_sandbox_executor(p.project_id)
        assert result["status"] == "blocked"
        assert result["secure_sandbox_status"] == "UNVERIFIED_ISOLATION"
        receipt = result["secure_sandbox_result"]
        assert receipt["passed"] is False
        assert receipt["observed_result"] == "UNKNOWN"
        assert receipt["identity_bound"] is False
        assert receipt["isolation_verified"] is False

        current = state_manager.get_project(p.project_id)
        assert current is not None
        assert current.stage == TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED


def test_untrusted_python_source_is_rejected():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)
        p = state_manager.create_project(objective="Test restricted execution boundary")

        with pytest.raises(PermissionError, match="trusted_internal"):
            restricted_python_executor(
                p.project_id,
                code_snippet="import os\nos.system('echo dangerous')",
            )

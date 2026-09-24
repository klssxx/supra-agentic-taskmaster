"""Tests for the provider-neutral Taskmaster facade and runner."""

import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
import supra_agentic.tools as tools_module
from supra_agentic.agent import TaskmasterAgent
from supra_agentic.models import (
    SECURE_SANDBOX_SEMANTICS_VERSION,
    SecureSandboxResult,
    TaskmasterStage,
)
from supra_agentic.providers import AgentProvider, ProviderResponse, ToolInput
from supra_agentic.runner import TaskmasterRunner
from supra_agentic.state import state_manager
from supra_agentic.tools import synthesize_strategy


class RecordingProvider(AgentProvider):
    """Small in-memory provider used to test the application boundary."""

    def __init__(self) -> None:
        self.messages: list[Mapping[str, Any]] = []

    @property
    def name(self) -> str:
        return "test-provider"

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "configured": True}

    def generate(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[ToolInput] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ProviderResponse:
        self.messages = list(messages)
        return ProviderResponse(
            text="provider response",
            provider=self.name,
            model=model or "test-model",
        )


def test_taskmaster_agent_delegates_to_selected_provider() -> None:
    provider = RecordingProvider()
    agent = TaskmasterAgent(provider, model_name="configured-model")

    response = agent.generate("Assess this objective")

    assert response.text == "provider response"
    assert response.provider == "test-provider"
    assert response.model == "configured-model"
    assert provider.messages[0]["role"] == "system"
    assert provider.messages[-1] == {"role": "user", "content": "Assess this objective"}


def test_runner_golden_path_execution(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)

        def _fake_sandbox(
            code: str,
            *,
            identity: dict[str, str],
            config=None,
            expected_output_marker=None,
        ):
            assert "SUPRA_SECURE_SANDBOX_OK" in code
            assert expected_output_marker == "SUPRA_SECURE_SANDBOX_OK"
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
        runner = TaskmasterRunner()
        posture = runner.run_golden_path(
            objective="Formulate an autonomous self-healing data pipeline for real-time telemetry",
            domain="data_pipeline",
        )

        assert posture.decomposition is not None
        assert posture.decomposition.domain == "data_pipeline"
        assert len(posture.candidates) == 3
        assert posture.selected_candidate is not None
        assert posture.verification is not None
        # contrato honesto: el verdict se deriva de la evidencia ejecutada,
        # nunca garantizado de antemano. NOT_EVALUATED es un estado válido,
        # pero ya no satisface el gate de completion.
        assert posture.verification.verdict in {"PASS", "CONDITIONAL_PASS", "FAIL", "NOT_EVALUATED"}
        assert 0.0 <= posture.verification.confidence_score <= 1.0
        assert len(posture.restricted_execution_results) >= 1
        assert posture.restricted_execution_results[-1].passed is True
        assert len(posture.secure_sandbox_results) == 1
        assert posture.secure_sandbox_results[-1].isolation_verified is True

        if posture.verification.verdict in {"PASS", "CONDITIONAL_PASS"}:
            assert posture.stage == TaskmasterStage.COMPLETED
            assert posture.final_output is not None
            assert "audit_sha256" in posture.final_output
            assert "null_hypothesis_h0" in posture.final_output
        else:
            assert posture.stage == TaskmasterStage.SECURE_SANDBOX_VERIFIED
            assert posture.final_output is None
            assert posture.checkpoints[-1].title == "Completion Gate Blocked"


def test_runner_self_correction_feedback():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)

        # 1. Initialize project
        p = state_manager.create_project(objective="Test Self-Correction Strategy Synthesis")
        pid = p.project_id

        # Decompose first
        from supra_agentic.tools import decompose_objective

        decompose_objective(pid, objective=p.objective)

        # Synthesize with error feedback
        feedback = "AssertionError: Database connection failed during burst mode"
        r = synthesize_strategy(
            pid, pathways_count=3, allow_disruptive=True, error_feedback=feedback
        )
        assert r["status"] == "success"
        assert r["self_correction_applied"] is True
        assert r["selected_candidate"]["paradigm_type"] == "DISRUPTIVE"
        assert "Compensatory" in r["selected_candidate"]["pathway_name"]

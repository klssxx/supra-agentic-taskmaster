"""Tests for the provider-neutral Taskmaster facade and runner."""

from collections.abc import Mapping, Sequence
from typing import Any

from supra_agentic.models import TaskmasterStage
from supra_agentic.agent import TaskmasterAgent
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


def test_runner_golden_path_execution():

    runner = TaskmasterRunner()
    posture = runner.run_golden_path(
        objective="Formulate an autonomous self-healing data pipeline for real-time telemetry",
        domain="data_pipeline",
    )

    assert posture.stage == TaskmasterStage.COMPLETED
    assert posture.decomposition is not None
    assert posture.decomposition.domain == "data_pipeline"
    assert len(posture.candidates) >= 3
    assert posture.selected_candidate is not None
    assert posture.verification is not None
    # contrato honesto: el verdict se deriva de la evidencia ejecutada,
    # nunca garantizado de antemano. NOT_EVALUATED es un estado válido.
    assert posture.verification.verdict in {"PASS", "CONDITIONAL_PASS", "FAIL", "NOT_EVALUATED"}
    assert 0.0 <= posture.verification.confidence_score <= 1.0
    assert len(posture.sandbox_results) >= 1
    assert posture.sandbox_results[-1].passed is True
    assert posture.final_output is not None
    assert "audit_sha256" in posture.final_output
    assert "null_hypothesis_h0" in posture.final_output
    assert len(posture.checkpoints) >= 5


def test_runner_self_correction_feedback():

    # 1. Initialize project
    p = state_manager.create_project(objective="Test Self-Correction Strategy Synthesis")
    pid = p.project_id

    # Decompose first
    from supra_agentic.tools import decompose_objective

    decompose_objective(pid, objective=p.objective)

    # Synthesize with error feedback
    feedback = "AssertionError: Database connection failed during burst mode"
    r = synthesize_strategy(pid, pathways_count=3, allow_disruptive=True, error_feedback=feedback)
    assert r["status"] == "success"
    assert r["self_correction_applied"] is True
    assert r["selected_candidate"]["paradigm_type"] == "DISRUPTIVE"
    assert "Compensatory" in r["selected_candidate"]["pathway_name"]

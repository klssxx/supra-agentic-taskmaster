"""Provider-neutral agent facade for SUPRA."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .providers import AgentProvider, ProviderResponse, ToolInput, get_provider

TASKMASTER_SYSTEM_INSTRUCTION = """You are SUPRA, an autonomous Taskmaster agent.

MISSION:
Decompose complex objectives, expose invariants and mutable assumptions,
synthesize competing causal strategies, verify them with explicit evidence,
run the fixed trusted internal restricted check, and produce an auditable deliverable.

OPERATING RULES:
- Separate facts, assumptions, hypotheses, and unverified claims.
- Prefer falsifiable experiments over persuasive prose.
- Never perform an uncontained side effect.
- Treat the deterministic SUPRA pipeline as the source of truth for stages,
  safety decisions, and audit evidence.
"""


class TaskmasterAgent:
    """Small provider-neutral facade used by the runner and HTTP API."""

    def __init__(
        self,
        provider: AgentProvider,
        *,
        model_name: str | None = None,
        agent_name: str = "supra_taskmaster_agent",
    ) -> None:
        self.provider = provider
        self.model_name = model_name
        self.agent_name = agent_name

    @property
    def provider_name(self) -> str:
        return self.provider.name

    def generate(
        self,
        prompt: str,
        *,
        tools: Sequence[ToolInput] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ProviderResponse:
        """Generate one response using the selected provider."""
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        messages: list[Mapping[str, Any]] = [
            {"role": "system", "content": TASKMASTER_SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt},
        ]
        return self.provider.generate(
            messages,
            tools=tools,
            model=model or self.model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def run(self, prompt: str) -> ProviderResponse:
        """Compatibility alias for simple programmatic callers."""
        return self.generate(prompt)


def create_taskmaster_agent(
    model_name: str | None = None,
    agent_name: str = "supra_taskmaster_agent",
    provider_name: str | None = None,
    provider: AgentProvider | None = None,
) -> TaskmasterAgent:
    """Create an agent without making a network request.

    Provider selection is controlled by ``provider_name`` or ``SUPRA_PROVIDER``.
    The returned object is lazy: endpoint availability is checked only when
    ``generate`` or ``provider.list_models`` is called.
    """
    selected_provider = provider or get_provider(provider_name)
    return TaskmasterAgent(
        selected_provider,
        model_name=model_name,
        agent_name=agent_name,
    )

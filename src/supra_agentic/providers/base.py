"""Provider contracts shared by every SUPRA model backend."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


class ProviderError(RuntimeError):
    """A provider rejected or could not complete a generation request."""


class ProviderUnavailable(ProviderError):
    """The configured provider endpoint could not be reached."""


@dataclass(frozen=True)
class ToolSpec:
    """Provider-neutral description of a callable tool."""

    name: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def as_openai_tool(self) -> dict[str, Any]:
        """Return the widely supported function-tool wire representation."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
            },
        }


@dataclass(frozen=True)
class ProviderResponse:
    """Normalized response independent of the selected backend."""

    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    model: str = ""


Message = Mapping[str, Any]
ToolInput = ToolSpec | Mapping[str, Any]


class AgentProvider(ABC):
    """Minimal synchronous/asynchronous contract for SUPRA providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider identifier used in telemetry and configuration."""
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolInput] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ProviderResponse:
        """Generate a response from a message list."""
        raise NotImplementedError

    async def generate_async(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolInput] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ProviderResponse:
        """Run the blocking provider contract without blocking an event loop."""
        return await asyncio.to_thread(
            self.generate,
            messages,
            tools=tools,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @abstractmethod
    def metadata(self) -> dict[str, Any]:
        """Return non-secret configuration metadata without network I/O."""
        raise NotImplementedError

"""SUPRA Taskmaster runner with deterministic safety and optional model help."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from .agent import TaskmasterAgent, create_taskmaster_agent
from .models import ProjectPosture
from .providers import AgentProvider, ProviderError
from .state import CompletionGateError, state_manager
from .tools import (
    decompose_objective,
    record_checkpoint,
    restricted_python_executor,
    secure_sandbox_executor,
    synthesize_strategy,
    verify_solution,
)

logger = logging.getLogger("supra_agentic.runner")


class TaskmasterRunner:
    """Executes the canonical Taskmaster workflow with independent completion gates."""

    def __init__(
        self,
        model_name: str | None = None,
        provider_name: str | None = None,
        provider: AgentProvider | None = None,
    ) -> None:
        self.model_name = model_name
        self.agent: TaskmasterAgent = create_taskmaster_agent(
            model_name=model_name,
            provider_name=provider_name,
            provider=provider,
        )

    @property
    def provider_name(self) -> str:
        """Return the configured provider without checking its availability."""
        return self.agent.provider_name

    def provider_metadata(self) -> dict[str, Any]:
        """Return safe provider metadata for health and telemetry endpoints."""
        return self.agent.provider.metadata()

    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """Generate model text through the configured provider."""
        return self.agent.generate(
            prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def run_golden_path(
        self,
        objective: str,
        project_id: str | None = None,
        domain: str = "general",
        allow_disruptive: bool = True,
        max_retries: int = 2,
        use_model: bool | None = None,
        model_prompt: str | None = None,
        criba_dossier_receipt: dict[str, Any] | None = None,
    ) -> ProjectPosture:
        """Execute the autonomous cycle with dynamic self-correction and isolation gates."""
        start_time = time.monotonic()
        clean_obj = objective.strip()
        if not clean_obj:
            raise ValueError("Objective cannot be empty.")

        if use_model is None:
            use_model = os.getenv("SUPRA_USE_MODEL", "false").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        model_assistance: dict[str, Any] = {
            "enabled": bool(use_model),
            "provider": self.provider_name,
        }
        if use_model:
            try:
                response = self.generate(model_prompt or clean_obj)
                model_assistance.update(
                    {
                        "status": "completed",
                        "model": response.model,
                        "text": response.text[:12000],
                        "tool_calls": response.tool_calls,
                    }
                )
            except ProviderError as exc:
                # Model help is optional. Do not persist provider exception
                # details into the project deliverable.
                model_assistance.update(
                    {
                        "status": "unavailable",
                        "error": "provider_assistance_unavailable",
                        "error_type": type(exc).__name__,
                    }
                )

        # Stage 1: Initialize Project (RECEIVED)
        posture = state_manager.create_project(
            objective=clean_obj,
            project_id=project_id,
            criba_dossier_receipt=criba_dossier_receipt,
        )
        pid = posture.project_id
        logger.info(f"[{pid}] Starting Taskmaster Golden Path for: '{clean_obj[:60]}...'")

        try:
            # Stage 2: Decompose (STRUCTURED)
            logger.info(f"[{pid}] Executing Tool 1: decompose_objective")
            decompose_objective(
                project_id=pid,
                objective=clean_obj,
                domain=domain,
            )

            # Stage 3: Synthesize Strategies (STRATIFIED)
            logger.info(f"[{pid}] Executing Tool 2: synthesize_strategy")
            synthesize_strategy(
                project_id=pid,
                pathways_count=3,
                allow_disruptive=allow_disruptive,
            )

            # Stage 4: verify invariants and run trusted restricted check
            logger.info(f"[{pid}] Executing Tool 3: verify_solution")
            verify_solution(project_id=pid)

            # Stage 4b: trusted restricted execution (no process isolation)
            logger.info(f"[{pid}] Executing Tool 4: restricted_python_executor")
            execution_res = restricted_python_executor(project_id=pid, fuzz_iterations=5)

            # Self-correct if the internal restricted check fails.
            retries = 0
            while (
                not execution_res["restricted_execution_result"]["passed"]
                or not execution_res["restricted_execution_result"]["identity_bound"]
            ) and retries < max_retries:
                retries += 1
                err_log = execution_res["restricted_execution_result"]["output_log"]
                logger.warning(
                    f"[{pid}] Restricted execution failed: '{err_log}'. "
                    f"Initiating self-correction loop #{retries}..."
                )

                # Re-synthesize strategy with feedback
                synthesize_strategy(
                    project_id=pid,
                    pathways_count=3,
                    allow_disruptive=True,
                    error_feedback=err_log,
                )

                # Re-verify and re-run the trusted internal check.
                verify_solution(project_id=pid)
                execution_res = restricted_python_executor(project_id=pid, fuzz_iterations=5)

            final_execution = execution_res["restricted_execution_result"]
            if not final_execution["passed"] or not final_execution["identity_bound"]:
                raise RuntimeError(
                    "restricted execution did not produce a bound passing result "
                    f"after {retries} correction attempt(s)"
                )

            # Stage 4c: externally isolated Docker sandbox.
            logger.info(f"[{pid}] Executing Tool 5: secure_sandbox_executor")
            sandbox_res = secure_sandbox_executor(project_id=pid)
            if sandbox_res["status"] != "success":
                logger.warning(
                    "[%s] Secure sandbox gate is blocked (%s); final checkpoint "
                    "will remain non-completed.",
                    pid,
                    sandbox_res["secure_sandbox_status"],
                )

            # Final Checkpoint & Deliverable Ledger (COMPLETED only if all gates pass)
            logger.info(f"[{pid}] Executing Tool 6: record_checkpoint")
            elapsed = time.monotonic() - start_time
            record_checkpoint(
                project_id=pid,
                deliverable_title=f"Autonomous Solution: {clean_obj[:50]}",
                summary=(
                    f"Taskmaster executed the canonical workflow in {elapsed:.2f}s "
                    f"(Self-Corrections: {retries})."
                ),
                provider_metadata=model_assistance,
            )

            final_posture = state_manager.get_project(pid)
            assert final_posture is not None
            logger.info(
                f"[{pid}] Taskmaster workflow COMPLETED in {elapsed:.2f}s; verification/scientific status remain separate."
            )
            return final_posture

        except CompletionGateError as exc:
            logger.warning("[%s] Completion gate blocked: %s", pid, exc)
            blocked_posture = state_manager.get_project(pid)
            assert blocked_posture is not None
            return blocked_posture
        except Exception as exc:
            error_type = type(exc).__name__
            logger.error("[%s] Taskmaster execution failed (%s)", pid, error_type)
            state_manager.fail_project(pid, f"Taskmaster execution failed ({error_type})")
            failed_posture = state_manager.get_project(pid)
            assert failed_posture is not None
            return failed_posture


# Global Singleton Runner
taskmaster_runner = TaskmasterRunner()

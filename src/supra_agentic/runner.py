"""SUPRA Taskmaster runner with deterministic safety and optional model help."""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from .agent import TaskmasterAgent, create_taskmaster_agent
from .models import ProjectPosture, TaskmasterStage
from .providers import AgentProvider, ProviderError
from .state import state_manager
from .tools import (
    decompose_objective,
    execute_sandbox_action,
    record_checkpoint,
    synthesize_strategy,
    verify_solution,
)

logger = logging.getLogger("supra_agentic.runner")


class TaskmasterRunner:
    """Executes the full 5-stage Taskmaster workflow autonomously with self-correction."""

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
    ) -> ProjectPosture:
        """Execute the 5-stage autonomous cycle with dynamic self-correction loops."""
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
        model_assistance: dict[str, Any] = {"enabled": bool(use_model), "provider": self.provider_name}
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
                # Model help is optional. The deterministic pipeline remains
                # authoritative when a local/cloud endpoint is unavailable.
                model_assistance.update({"status": "unavailable", "error": str(exc)})

        # Stage 1: Initialize Project (RECEIVED)
        posture = state_manager.create_project(objective=clean_obj, project_id=project_id)
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

            # INTEGRACIÓN CRIBA ↔ SUPRA: Enriquecer candidatos con CRIBA
            logger.info(f"[{pid}] Executing CRIBA Bridge: generating ideas via CRIBA")
            try:
                from .integrations.criba_bridge import call_criba
                criba_result = call_criba(
                    query=clean_obj,
                    mode="balanced",
                    supporting_methods=6,
                )
                criba_ideas = criba_result.get("ideas") or criba_result.get("innovation", {}).get("ideas") or []
                logger.info(f"[{pid}] CRIBA generated {len(criba_ideas)} ideas")
                
                # Convertir ideas CRIBA a StrategyCandidates de SUPRA
                from .models import StrategyCandidate
                criba_candidates = []
                for i, idea in enumerate(criba_ideas[:5]):  # Top 5 ideas de CRIBA
                    conv = idea.get("convergence", {})
                    candidate = StrategyCandidate(
                        pathway_name=f"CRIBA: {idea.get('title', f'Idea {i+1}')[:60]}",
                        paradigm_type="ORTHOGONAL" if conv.get("divergence_real") else "CONSERVATIVE",
                        hypothesis=idea.get("description", "")[:200],
                        action_plan=[
                            f"Mechanism: {idea.get('mechanism_causal', '')[:100]}",
                            f"Expected effect: {idea.get('expected_effect', '')[:100]}",
                        ],
                        divergence_score=min(0.95, conv.get("novelty", 0.5) + 0.3),
                        feasibility_score=conv.get("evidence", 0.5),
                        is_selected=False,
                    )
                    criba_candidates.append(candidate)
                
                if criba_candidates:
                    # Añadir candidatos de CRIBA a SUPRA
                    posture = state_manager.get_project(pid)
                    if posture:
                        all_candidates = list(posture.candidates) + criba_candidates
                        state_manager.add_candidates(pid, all_candidates, select_best=True)
                        logger.info(f"[{pid}] Added {len(criba_candidates)} CRIBA candidates to SUPRA")
            except Exception as e:
                logger.warning(f"[{pid}] CRIBA bridge failed (non-critical): {e}")

            # Stage 4: Verify Invariants & Sandbox with Self-Correction
            logger.info(f"[{pid}] Executing Tool 3: verify_solution")
            verify_solution(project_id=pid)

            # FASE 3: Verificación causal (SUPRA razona causalmente)
            logger.info(f"[{pid}] Executing Causal Verification")
            from .causal import CausalGraph, CausalVerifier
            posture = state_manager.get_project(pid)
            if posture and posture.decomposition and posture.selected_candidate:
                graph = CausalGraph.from_decomposition(posture.decomposition)
                verifier = CausalVerifier(graph)
                causal_result = verifier.check_candidate(posture.selected_candidate)
                logger.info(f"[{pid}] Causal confidence: {causal_result['causal_confidence']}")

            # Stage 4b: Sandbox Execution (SANDBOX_VERIFIED)
            logger.info(f"[{pid}] Executing Tool 4: execute_sandbox_action")
            sb_res = execute_sandbox_action(project_id=pid, fuzz_iterations=5)

            # Self-Correction Loop: If sandbox fails, re-synthesize with error feedback
            retries = 0
            while not sb_res["sandbox_result"]["passed"] and retries < max_retries:
                retries += 1
                err_log = sb_res["sandbox_result"]["output_log"]
                logger.warning(f"[{pid}] Sandbox check failed: '{err_log}'. Initiating self-correction loop #{retries}...")
                
                # Re-synthesize strategy with feedback
                synthesize_strategy(
                    project_id=pid,
                    pathways_count=3,
                    allow_disruptive=True,
                    error_feedback=err_log,
                )
                
                # Re-verify and re-execute sandbox
                verify_solution(project_id=pid)
                sb_res = execute_sandbox_action(project_id=pid, fuzz_iterations=5)

            # Stage 5: Final Checkpoint & Deliverable Ledger (COMPLETED)
            logger.info(f"[{pid}] Executing Tool 5: record_checkpoint")
            elapsed = time.monotonic() - start_time
            record_checkpoint(
                project_id=pid,
                deliverable_title=f"Autonomous Solution: {clean_obj[:50]}",
                summary=f"Taskmaster completed all 5 stages in {elapsed:.2f}s (Self-Corrections: {retries}).",
                provider_metadata=model_assistance,
            )

            final_posture = state_manager.get_project(pid)
            assert final_posture is not None
            logger.info(f"[{pid}] Taskmaster Golden Path COMPLETED successfully in {elapsed:.2f}s.")
            return final_posture

        except Exception as exc:
            logger.error(f"[{pid}] Taskmaster execution encountered an error: {exc}")
            state_manager.fail_project(pid, str(exc))
            failed_posture = state_manager.get_project(pid)
            assert failed_posture is not None
            return failed_posture


# Global Singleton Runner
taskmaster_runner = TaskmasterRunner()

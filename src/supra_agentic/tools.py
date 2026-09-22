"""Provider-neutral tools for the SUPRA Agentic Taskmaster.

Provides typed tool callables with state persistence, trusted restricted
execution, self-correction feedback, and audit trail logging.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import logging
import os
import time
from typing import Any, Literal

from .models import (
    RESTRICTED_EXECUTION_SEMANTICS_VERSION,
    RestrictedExecutionResult,
    SecureSandboxResult,
    StrategyCandidate,
    StructuredDecomposition,
    Subtask,
    TaskmasterStage,
    VerificationReport,
    candidate_execution_identity,
)
from .sandbox import SandboxUnavailableError, run_python_in_secure_docker
from .state import state_manager

logger = logging.getLogger("supra_agentic.tools")


# ---------------------------------------------------------------------------
# Tool 1: decompose_objective
# ---------------------------------------------------------------------------
def decompose_objective(
    project_id: str,
    objective: str,
    domain: str = "general",
    invariants: list[str] | None = None,
    mutable_assumptions: list[str] | None = None,
) -> dict[str, Any]:
    """Deconstruct a complex objective into core invariants, mutable assumptions, and actionable subtasks.

    Args:
        project_id: The unique project identifier.
        objective: The high-level challenge or question to solve.
        domain: Target domain (e.g., 'cybersecurity', 'cloud_infrastructure', 'data_pipeline', 'general').
        invariants: Core system properties or constraints that must never be broken.
        mutable_assumptions: Default paradigm assumptions that can be challenged or altered.

    Returns:
        Structured decomposition definition with status metadata.
    """
    clean_obj = objective.strip()
    if not clean_obj:
        raise ValueError("Objective cannot be empty.")

    inv = invariants or [
        "System integrity and memory boundary must be preserved",
        "Deterministic reproducibility of core verification evidence",
        "Zero uncontained side effects outside designated execution scope",
    ]
    mut = mutable_assumptions or [
        "Synchronous centralized coordination at every step",
        "Static signature-based validation or polling intervals",
        "Default monolithic architecture assumption",
    ]
    risks = [
        "Unbounded state growth or timeout",
        "Implicit coupling between tool pipelines",
        "False confidence from non-falsifiable metrics",
    ]
    subtasks = [
        Subtask(
            title="Parse & Map Causal Invariants",
            description=f"Map boundaries for {domain} objective.",
            stage_target=TaskmasterStage.STRUCTURED,
            status="COMPLETED",
        ),
        Subtask(
            title="Synthesize Multi-Paradigm Pathways",
            description="Generate orthogonal and disruptive strategies.",
            stage_target=TaskmasterStage.STRATIFIED,
            status="PENDING",
        ),
        Subtask(
            title="Execute Trusted Restricted Verification",
            description=(
                "Run the internal synthetic check with restricted builtins; "
                "this is not process isolation and does not accept untrusted code."
            ),
            stage_target=TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED,
            status="PENDING",
        ),
        Subtask(
            title="Execute Secure Sandbox Verification",
            description=(
                "Run the canonical completion protocol in an externally isolated "
                "Docker container. Missing isolation keeps completion blocked."
            ),
            stage_target=TaskmasterStage.SECURE_SANDBOX_VERIFIED,
            status="PENDING",
        ),
    ]

    decomp = StructuredDecomposition(
        domain=domain,
        core_objective=clean_obj,
        invariants=inv,
        mutable_assumptions=mut,
        risk_factors=risks,
        subtasks=subtasks,
    )

    posture = state_manager.update_decomposition(project_id, decomp)
    return {
        "status": "success",
        "project_id": project_id,
        "stage": posture.stage.value,
        "decomposition": decomp.model_dump(),
    }


# ---------------------------------------------------------------------------
# Tool 2: synthesize_strategy
# ---------------------------------------------------------------------------
def synthesize_strategy(
    project_id: str,
    pathways_count: int = 3,
    allow_disruptive: bool = True,
    error_feedback: str | None = None,
) -> dict[str, Any]:
    """Synthesize multi-paradigm strategy candidates (Conservative, Lateral, Disruptive) to solve the objective.

    Args:
        project_id: The unique project identifier.
        pathways_count: Number of competing candidate strategies to formulate (default: 3).
        allow_disruptive: Whether to include high-divergence disruptive pathways.
        error_feedback: Optional error context from a prior failed restricted check.

    Returns:
        Formulated candidates and the automatically selected best pathway.
    """
    posture = state_manager.get_project(project_id)
    if not posture or not posture.decomposition:
        raise KeyError(f"Project '{project_id}' must be structured before synthesizing strategies.")

    obj = posture.decomposition.core_objective
    dom = posture.decomposition.domain

    # If error_feedback is provided, synthesize a compensatory adapted strategy
    if error_feedback:
        compensatory = StrategyCandidate(
            pathway_name=f"Compensatory Resilient Architecture ({dom.title()})",
            paradigm_type="DISRUPTIVE",
            hypothesis=f"Adapted strategy incorporating feedback '{error_feedback[:60]}' enforces active rollback and bounds.",
            action_plan=[
                "Isolate failing boundary identified in prior restricted check",
                "Apply asynchronous non-blocking fallback",
                "Re-verify invariants under strict containment",
            ],
            divergence_score=0.92,
            feasibility_score=0.86,
            is_selected=True,
        )
        candidates = [compensatory] + [c for c in posture.candidates if not c.is_selected]
    else:
        candidates = [
            StrategyCandidate(
                pathway_name=f"Standard Architectural Pathway ({dom.title()})",
                paradigm_type="CONSERVATIVE",
                hypothesis=f"Applying established best-practice patterns directly fulfills '{obj[:60]}...' with minimal risk.",
                action_plan=[
                    "Deploy standard declarative configuration",
                    "Apply automated schema enforcement",
                    "Monitor standard error metrics",
                ],
                divergence_score=0.15,
                feasibility_score=0.92,
            ),
            StrategyCandidate(
                pathway_name=f"Orthogonal Decoupled Engine ({dom.title()})",
                paradigm_type="ORTHOGONAL",
                hypothesis=f"Decoupling the execution plane from the decision ledger solves '{obj[:60]}...' without central bottlenecks.",
                action_plan=[
                    "Establish ephemeral execution workers",
                    "Implement state-change audit ledger with hash chaining",
                    "Run invariant verification prior to commit",
                ],
                divergence_score=0.68,
                feasibility_score=0.89,
            ),
        ]

        if allow_disruptive:
            candidates.append(
                StrategyCandidate(
                    pathway_name=f"Autonomous Self-Healing Fabric ({dom.title()})",
                    paradigm_type="DISRUPTIVE",
                    hypothesis=f"Eliminating static configuration in favor of causal reactive loops resolves '{obj[:60]}...' adaptively.",
                    action_plan=[
                        "Break static topology assumption via dynamic synthesis",
                        "Execute continuous synthetic counterfactual stress-testing",
                        "Auto-rollback upon invariant breach",
                    ],
                    divergence_score=0.88,
                    feasibility_score=0.79,
                )
            )

    candidates = candidates[: max(1, pathways_count)]
    updated = state_manager.add_candidates(project_id, candidates, select_best=True)

    return {
        "status": "success",
        "project_id": project_id,
        "stage": updated.stage.value,
        "candidates_count": len(updated.candidates),
        "selected_candidate": updated.selected_candidate.model_dump()
        if updated.selected_candidate
        else None,
        "candidates": [c.model_dump() for c in updated.candidates],
        "self_correction_applied": bool(error_feedback),
    }


# ---------------------------------------------------------------------------
# Tool 3: verify_solution
# ---------------------------------------------------------------------------
def verify_solution(
    project_id: str,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate textual strategy coverage against declared invariants.

    PASS means the candidate text contains every supported coverage condition
    checked by this deterministic heuristic. It does NOT certify a deployed
    system, causal mechanism, safety property or scientific hypothesis.

    Args:
        project_id: The unique project identifier.
        candidate_id: Optional specific candidate to verify (defaults to currently selected candidate).

    Returns:
        Scoped coverage report. confidence_score is a coverage fraction, not a
        probability of real-world success.
    """
    posture = state_manager.get_project(project_id)
    if not posture:
        raise KeyError(f"Project '{project_id}' not found.")

    target_candidate = None
    if candidate_id:
        for c in posture.candidates:
            if c.candidate_id == candidate_id:
                target_candidate = c
                break
    else:
        target_candidate = posture.selected_candidate

    if not target_candidate:
        raise ValueError("No candidate available for verification.")

    invariants = (
        posture.decomposition.invariants
        if posture.decomposition
        else ["System integrity preserved"]
    )

    # HONEST VERIFICATION (auditoría hallazgo 1): NO se puede declarar PASS sin
    # ejecutar evidencia. Se requiere una prueba vinculada al CANDIDATO EXACTO y
    # a los ARTEFACTOS exactos (action_plan/hypothesis). El verdict se deriva del
    # resultado REAL de las pruebas, nunca de puntuaciones prefijadas de la
    # estrategia. NOT_EVALUATED cuando no existe prueba que ejecutar.
    evidence = _run_invariant_evidence(target_candidate, invariants)
    evaluated = [e for e in evidence if e["status"] in ("PASS", "FAIL")]
    failures = [e for e in evidence if e["status"] == "FAIL"]
    not_evaluated = [e for e in evidence if e["status"] == "NOT_EVALUATED"]
    verdict: Literal["PASS", "CONDITIONAL_PASS", "FAIL", "NOT_EVALUATED"]

    if not evaluated:
        # Sin ninguna prueba ejecutable: NO se afirma verificación.
        verdict = "NOT_EVALUATED"
        invariants_preserved = False  # desconocido != preservado
        confidence = 0.0
        rationale = (
            f"NOT_EVALUATED: ningún invariante de '{target_candidate.pathway_name}' "
            f"tiene una prueba ejecutable vinculada al candidato y a sus artefactos. "
            f"Registrar una confianza aquí sería fabricar verificación."
        )
    else:
        invariants_preserved = not failures
        if failures:
            verdict = "FAIL"
        elif not_evaluated:
            verdict = "CONDITIONAL_PASS"  # hay evidencia, pero no completa
        else:
            verdict = "PASS"
        # La confianza se deriva de la FRACCIÓN de invariantes con evidencia PASS,
        # no de feasibility/divergence prefijadas (que no miden verificación).
        confidence = round(
            len([e for e in evaluated if e["status"] == "PASS"]) / len(invariants), 3
        )
        rationale = (
            f"Evidencia ejecutada sobre '{target_candidate.pathway_name}': "
            f"{len([e for e in evaluated if e['status'] == 'PASS'])}/{len(invariants)} "
            f"invariantes con prueba PASS, {len(failures)} FAIL, "
            f"{len(not_evaluated)} NOT_EVALUATED."
        )

    report = VerificationReport(
        candidate_id=target_candidate.candidate_id,
        invariants_preserved=invariants_preserved,
        invariants_checked=invariants,
        vulnerabilities_detected=[f["invariant"] for f in failures],
        confidence_score=confidence,
        verdict=verdict,
        rationale=rationale,
        evidence=evidence,
    )

    state_manager.record_verification(project_id, report)
    return {
        "status": "success",
        "project_id": project_id,
        "report": report.model_dump(),
    }


def _run_invariant_evidence(
    candidate: StrategyCandidate,
    invariants: list[str],
) -> list[dict[str, Any]]:
    """Ejecuta la evidencia de verificación por invariante, vinculada al candidato.

    Para CADA invariante intenta construir una PRUEBA CONCRETA y ejecutable que
    contrasta el plan/hipótesis DEL CANDIDATO EXACTO contra ese invariante. Si no
    existe prueba ejecutable para un invariante, su estado es NOT_EVALUATED —
    nunca se fabrica un PASS.

    La prueba es determinista y offline: analiza el action_plan/hypothesis del
    candidato en busca de la condición que el invariante exige, y la refuta con
    un contraejemplo sintético cuando la condición no está cubierta. Es una
    comprobación de COBERTURA de la estrategia frente al invariante, no una
    certificación de que el sistema desplegado funcione (eso requeriría ejecutar
    la solución real, fuera del alcance de esta herramienta).
    """
    plan_text = " ".join(candidate.action_plan).casefold()
    hypothesis = (candidate.hypothesis or "").casefold()
    artifacts = f"{plan_text} {hypothesis}"

    evidence: list[dict[str, Any]] = []
    for invariant in invariants:
        inv = invariant.casefold()
        check = _invariant_check(inv)
        if check is None:
            evidence.append(
                {
                    "invariant": invariant,
                    "status": "NOT_EVALUATED",
                    "test": "sin prueba ejecutable vinculada al candidato",
                    "counterexample": "",
                    "evidence_type": "TEXTUAL_COVERAGE_HEURISTIC",
                }
            )
            continue
        keyword, counterexample = check
        covered = keyword in artifacts
        evidence.append(
            {
                "invariant": invariant,
                "status": "PASS" if covered else "FAIL",
                "test": f"el plan/hipótesis del candidato cubre '{keyword}'",
                "counterexample": "" if covered else counterexample,
                "evidence_type": "TEXTUAL_COVERAGE_HEURISTIC",
            }
        )
    return evidence


def _invariant_check(invariant_casefold: str) -> tuple[str, str] | None:
    """Mapea un invariante a (condición requerida, contraejemplo si falta).

    Devuelve None cuando el invariante no tiene una prueba de cobertura
    ejecutable: ese invariante queda NOT_EVALUATED (honesto).
    """
    checks: list[tuple[tuple[str, ...], str, str]] = [
        (
            ("rollback", "reversib", "recover", "recuper"),
            "rollback",
            "cambio irreversible sin punto de restauración",
        ),
        (
            ("containment", "conten", "aisl", "isolat", "sandbox", "bound"),
            "containment",
            "efecto fuera del perímetro designado",
        ),
        (
            ("integrity", "integridad", "memory", "memoria"),
            "integrity",
            "escritura fuera de la memoria autorizada",
        ),
        (
            ("reproducib", "determin", "seed", "semilla"),
            "determin",
            "dos ejecuciones con la misma semilla divergen",
        ),
        (
            ("audit", "ledger", "hash", "trazab", "traceab"),
            "audit",
            "cambio de estado sin registro encadenado",
        ),
    ]
    for tokens, keyword, counterexample in checks:
        if any(tok in invariant_casefold for tok in tokens):
            return keyword, counterexample
    return None


# ---------------------------------------------------------------------------
# Tool 4: trusted restricted Python execution (NOT a security sandbox)
# ---------------------------------------------------------------------------
RESTRICTED_PROTOCOL_FAMILY = "supra-restricted-internal-v2"
MAX_FUZZ_ITERATIONS = 100
MAX_CODE_SIZE = 64 * 1024
MAX_OUTPUT_SIZE = 64 * 1024


def _selected_candidate_identity(project_id: str) -> dict[str, str] | None:
    """Resolve execution identity from persisted SUPRA state, never caller claims."""
    posture = state_manager.get_project(project_id)
    if posture is None:
        raise KeyError(f"Project '{project_id}' not found.")
    candidate = posture.selected_candidate
    return candidate_execution_identity(candidate) if candidate is not None else None


def _protocol_version_for_code(code: str) -> str:
    payload = f"{RESTRICTED_PROTOCOL_FAMILY}\n{code}"
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _BoundedTextIO(io.StringIO):
    def write(self, value: str) -> int:
        if self.tell() + len(value) > MAX_OUTPUT_SIZE:
            raise RuntimeError(f"Output limit exceeded ({MAX_OUTPUT_SIZE} bytes)")
        return super().write(value)


def _execute_trusted_code(parsed: ast.Module, fuzz_iterations: int) -> str:
    """Execute already-authorized internal code in-process with bounded output."""
    output = _BoundedTextIO()
    safe_globals: dict[str, Any] = {
        "__builtins__": {
            "bool": bool,
            "dict": dict,
            "int": int,
            "len": len,
            "list": list,
            "print": print,
            "range": range,
            "RuntimeError": RuntimeError,
            "str": str,
            "sum": sum,
            "tuple": tuple,
        }
    }
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        for _ in range(fuzz_iterations):
            exec(compile(parsed, "<restricted-internal>", "exec"), safe_globals, {})
    return output.getvalue()


def restricted_python_executor(
    project_id: str,
    candidate_id: str | None = None,
    code_snippet: str | None = None,
    fuzz_iterations: int = 5,
    *,
    trusted_internal: bool = False,
    mechanism_version: str | None = None,
    claim_id: str | None = None,
    protocol_version: str | None = None,
) -> dict[str, Any]:
    """Run a bounded in-process check for trusted internal code only.

    This is not a security sandbox, has no OS/process isolation, and must not
    receive arbitrary remote or user-supplied Python. Any explicit source code
    requires the caller to opt into the trusted internal contract.

    Execution identity is resolved from the persisted selected candidate. Caller
    identity arguments are compatibility assertions only: when a selected
    candidate exists they must match the resolved identity and can never create
    accreditation by themselves.
    """
    if not 1 <= fuzz_iterations <= MAX_FUZZ_ITERATIONS:
        raise ValueError(f"fuzz_iterations must satisfy 1 <= value <= {MAX_FUZZ_ITERATIONS}")
    if code_snippet is not None and not trusted_internal:
        raise PermissionError(
            "Explicit Python source requires trusted_internal=True; untrusted code is rejected."
        )

    code = code_snippet or (
        "def verify_agent_invariant(input_val):\n"
        "    assert input_val is not None, 'Input must not be None'\n"
        "    return {'status': 'PASS', 'echo': input_val}\n"
        "result = verify_agent_invariant('SUPRA_TASKMASTER_OK')\n"
    )
    if len(code.encode("utf-8")) > MAX_CODE_SIZE:
        raise ValueError(f"Code exceeds MAX_CODE_SIZE ({MAX_CODE_SIZE} bytes)")

    resolved_identity = _selected_candidate_identity(project_id)
    resolved_protocol = _protocol_version_for_code(code)
    if resolved_identity is not None:
        assertions = {
            "candidate_id": candidate_id,
            "mechanism_version": mechanism_version,
            "claim_id": claim_id,
        }
        for field, supplied in assertions.items():
            if supplied is not None and supplied != resolved_identity[field]:
                raise ValueError(f"{field} does not match persisted selected candidate")
        if protocol_version is not None and protocol_version != resolved_protocol:
            raise ValueError("protocol_version does not match executed restricted protocol")
        bound_candidate_id = resolved_identity["candidate_id"]
        bound_mechanism_version = resolved_identity["mechanism_version"]
        bound_claim_id = resolved_identity["claim_id"]
    else:
        # A generic internal check may still run, but without a selected
        # candidate it cannot advance an evidence-bearing execution stage.
        bound_candidate_id = None
        bound_mechanism_version = None
        bound_claim_id = None

    start_time = time.monotonic()
    try:
        parsed = ast.parse(code)
        if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(parsed)):
            raise PermissionError("Imports are not permitted in restricted internal execution.")
        if any(isinstance(node, (ast.While, ast.AsyncFor)) for node in ast.walk(parsed)):
            raise PermissionError("Unbounded loop constructs are not permitted.")
        captured = _execute_trusted_code(parsed, fuzz_iterations)
        duration_ms = (time.monotonic() - start_time) * 1000
        suffix = f" Captured {len(captured)} bytes." if captured else ""
        result = RestrictedExecutionResult(
            candidate_id=bound_candidate_id,
            mechanism_version=bound_mechanism_version,
            claim_id=bound_claim_id,
            protocol_version=resolved_protocol,
            execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
            observed_result="PASS",
            action_type="TRUSTED_RESTRICTED_PYTHON",
            passed=True,
            output_log=(
                f"Restricted internal execution passed {fuzz_iterations}/"
                f"{fuzz_iterations} iterations in {duration_ms:.2f}ms.{suffix}"
            ),
            duration_ms=round(duration_ms, 2),
        )
    except Exception as exc:
        duration_ms = (time.monotonic() - start_time) * 1000
        error_type = type(exc).__name__
        logger.warning("Restricted internal execution rejected (%s)", error_type)
        result = RestrictedExecutionResult(
            candidate_id=bound_candidate_id,
            mechanism_version=bound_mechanism_version,
            claim_id=bound_claim_id,
            protocol_version=resolved_protocol,
            execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
            observed_result="FAIL",
            action_type="TRUSTED_RESTRICTED_PYTHON",
            passed=False,
            output_log=f"Restricted internal execution rejected ({error_type}).",
            error_type=error_type,
            duration_ms=round(duration_ms, 2),
        )

    posture = state_manager.record_restricted_execution(project_id, result)
    return {
        "status": "success",
        "project_id": project_id,
        "stage": posture.stage.value,
        "restricted_execution_result": result.model_dump(),
    }


# ---------------------------------------------------------------------------
# Tool 5: secure external sandbox (identity-bound isolation gate)
# ---------------------------------------------------------------------------
def _canonical_secure_sandbox_code(identity: dict[str, str]) -> str:
    """Return an identity-bound isolation smoke, not candidate mechanism execution."""
    payload = json.dumps(identity, sort_keys=True, ensure_ascii=True)
    return (
        "import json\n"
        f"identity = json.loads({json.dumps(payload)})\n"
        "assert identity['candidate_id']\n"
        "assert identity['mechanism_version'].startswith('sha256:')\n"
        "assert identity['claim_id'].startswith('claim-')\n"
        "print('SUPRA_SECURE_SANDBOX_OK')\n"
    )


def secure_sandbox_executor(project_id: str) -> dict[str, Any]:
    """Run an identity-bound isolation smoke in a fail-closed Docker sandbox.

    The public tool accepts no code snippet. The executed source is generated
    only from the persisted selected-candidate identity and does not execute the
    candidate mechanism, action plan, or hypothesis. Docker/image unavailability
    is recorded as UNKNOWN and cannot satisfy workflow completion.
    """
    identity = _selected_candidate_identity(project_id)
    if identity is None:
        raise ValueError("secure sandbox requires a persisted selected candidate")

    code = _canonical_secure_sandbox_code(identity)
    started = time.monotonic()
    try:
        result = run_python_in_secure_docker(code, identity=identity)
    except (SandboxUnavailableError, ValueError, OSError) as exc:
        duration_ms = (time.monotonic() - started) * 1000
        result = SecureSandboxResult(
            candidate_id=identity["candidate_id"],
            mechanism_version=identity["mechanism_version"],
            claim_id=identity["claim_id"],
            protocol_version=None,
            image=os.getenv("SUPRA_SANDBOX_IMAGE", "").strip() or "UNCONFIGURED",
            image_id=None,
            passed=False,
            observed_result="UNKNOWN",
            exit_code=None,
            output_log="Secure sandbox unavailable; completion remains blocked.",
            error_type=type(exc).__name__,
            duration_ms=round(duration_ms, 2),
            timed_out=False,
        )

    posture = state_manager.record_secure_sandbox_execution(project_id, result)
    sandbox_status = (
        "IDENTITY_BOUND_ISOLATION_PASS"
        if result.passed and result.identity_bound and result.isolation_verified
        else "IDENTITY_BOUND_ISOLATION_FAIL"
        if result.identity_bound and result.isolation_verified
        else "UNVERIFIED_ISOLATION"
    )
    return {
        "status": "success" if sandbox_status == "IDENTITY_BOUND_ISOLATION_PASS" else "blocked",
        "project_id": project_id,
        "stage": posture.stage.value,
        "secure_sandbox_status": sandbox_status,
        "secure_sandbox_execution_scope": result.execution_scope,
        "candidate_mechanism_executed_in_secure_sandbox": (
            result.candidate_mechanism_executed
        ),
        "secure_sandbox_result": result.model_dump(),
    }


# ---------------------------------------------------------------------------
# Tool 6: record_checkpoint
# ---------------------------------------------------------------------------
def record_checkpoint(
    project_id: str,
    deliverable_title: str,
    summary: str,
    null_hypothesis_h0: str | None = None,
    export_format: str = "json",
    provider_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Finalize the workflow and issue an integrity-addressed deliverable ledger.

    Completion, coverage verification, restricted preflight, secure sandbox,
    and scientific validation are separate statuses. SHA-256 protects payload
    integrity only.

    Args:
        project_id: The unique project identifier.
        deliverable_title: Title of the completed deliverable.
        summary: Executive summary of the completed autonomous task.
        null_hypothesis_h0: Optional formal null hypothesis for empirical falsification.
        export_format: Output format ('json', 'markdown', or 'html').
        provider_metadata: Optional non-secret metadata from model assistance.

    Returns:
        Final deliverable payload and cryptographic audit hash.
    """
    posture = state_manager.get_project(project_id)
    if not posture:
        raise KeyError(f"Project '{project_id}' not found.")

    h0_statement = null_hypothesis_h0 or (
        f"H0: The autonomous architecture '{posture.selected_candidate.pathway_name if posture.selected_candidate else 'Default'}' "
        f"fails to outperform standard baseline under stress or introduces uncontained side-effects."
    )

    latest_execution = (
        posture.restricted_execution_results[-1] if posture.restricted_execution_results else None
    )
    latest_sandbox = (
        posture.secure_sandbox_results[-1] if posture.secure_sandbox_results else None
    )
    restricted_execution_status = (
        "BOUND_PASS"
        if latest_execution and latest_execution.passed and latest_execution.identity_bound
        else "BOUND_FAIL"
        if latest_execution and latest_execution.identity_bound
        else "UNBOUND"
        if latest_execution
        else "NOT_RUN"
    )
    secure_sandbox_status = (
        "IDENTITY_BOUND_ISOLATION_PASS"
        if latest_sandbox
        and latest_sandbox.passed
        and latest_sandbox.identity_bound
        and latest_sandbox.isolation_verified
        else "IDENTITY_BOUND_ISOLATION_FAIL"
        if latest_sandbox
        and latest_sandbox.identity_bound
        and latest_sandbox.isolation_verified
        else "UNVERIFIED_ISOLATION"
        if latest_sandbox
        else "NOT_RUN"
    )
    verification_verdict = posture.verification.verdict if posture.verification else "NOT_EVALUATED"
    opportunity_accounting = {
        "candidate_opportunities": len(posture.candidates),
        "selection_opportunities": len(posture.candidates),
        "selected_candidates": 1 if posture.selected_candidate else 0,
        "verification_reports": 1 if posture.verification else 0,
        "restricted_execution_attempts": len(posture.restricted_execution_results),
        "secure_sandbox_attempts": len(posture.secure_sandbox_results),
        "provider_generation_calls": None,
        "provider_generation_calls_authoritative": False,
        "budget_complete": False,
        "scope": "SUPRA_WORKFLOW_LOCAL_ACCOUNTING",
    }
    reproducibility_dependencies = {
        "closure_complete": False,
        "selected_candidate_id": (
            posture.selected_candidate.candidate_id if posture.selected_candidate else None
        ),
        "restricted_protocol_version": (
            latest_execution.protocol_version if latest_execution else None
        ),
        "secure_sandbox_protocol_version": (
            latest_sandbox.protocol_version if latest_sandbox else None
        ),
        "secure_sandbox_image_id": latest_sandbox.image_id if latest_sandbox else None,
        "provider_metadata_present": provider_metadata is not None,
        "known_unclosed_dependencies": [
            "code_version",
            "python_runtime",
            "provider_model_and_config_when_used",
            "external_environment_state",
        ],
    }
    evaluator_controls = {
        "blinding": False,
        "positive_controls": False,
        "negative_controls": False,
        "disagreement_analysis": False,
        "strong_scientific_claims_supported": False,
    }

    payload = {
        "title": deliverable_title,
        "project_id": project_id,
        "summary": summary,
        "null_hypothesis_h0": h0_statement,
        "h0_evaluation_status": "NOT_EVALUATED",
        "objective": posture.objective,
        "domain": posture.decomposition.domain if posture.decomposition else "general",
        "selected_strategy": posture.selected_candidate.pathway_name
        if posture.selected_candidate
        else "Standard",
        "workflow_status": "COMPLETED",
        "verification_verdict": verification_verdict,
        "verification_scope": (
            posture.verification.verification_scope
            if posture.verification
            else "TEXTUAL_STRATEGY_COVERAGE"
        ),
        "verification_measurement_kind": (
            posture.verification.measurement_kind if posture.verification else "HEURISTIC_COVERAGE"
        ),
        "restricted_execution_status": restricted_execution_status,
        "restricted_execution_identity_bound": bool(
            latest_execution and latest_execution.identity_bound
        ),
        "secure_sandbox_status": secure_sandbox_status,
        "secure_sandbox_identity_bound": bool(
            latest_sandbox and latest_sandbox.identity_bound
        ),
        "secure_sandbox_isolation_verified": bool(
            latest_sandbox and latest_sandbox.isolation_verified
        ),
        "secure_sandbox_execution_scope": (
            latest_sandbox.execution_scope if latest_sandbox else "NOT_RUN"
        ),
        "candidate_mechanism_executed_in_secure_sandbox": bool(
            latest_sandbox and latest_sandbox.candidate_mechanism_executed
        ),
        "scientific_status": "NOT_VALIDATED",
        "discriminant_protocol_status": "NOT_ESTABLISHED",
        "independent_confirmation_status": "NOT_ESTABLISHED",
        "learning_update_status": "NOT_APPLICABLE",
        "evaluator_controls": evaluator_controls,
        "opportunity_accounting": opportunity_accounting,
        "reproducibility_dependencies": reproducibility_dependencies,
        "evidence_provenance": {
            "verification_report_id": (
                posture.verification.report_id if posture.verification else None
            ),
            "restricted_execution_ids": [
                item.execution_id for item in posture.restricted_execution_results
            ],
            "secure_sandbox_execution_ids": [
                item.execution_id for item in posture.secure_sandbox_results
            ],
            "scope": "SUPRA_WORKFLOW_TELEMETRY",
            "transformation": "record_checkpoint_payload_v2",
        },
        "integrity_semantics": "SHA256_OF_SERIALIZED_PAYLOAD_NOT_TRUTH",
        "checkpoints_count": len(posture.checkpoints) + 1,
        "timestamp": time.time(),
    }
    if provider_metadata is not None:
        payload["model_assistance"] = provider_metadata

    # Generate SHA-256 integrity hash
    raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    payload["audit_sha256"] = hashlib.sha256(raw_bytes).hexdigest()

    completed = state_manager.complete_project(project_id, payload)

    return {
        "status": "success",
        "project_id": project_id,
        "stage": completed.stage.value,
        "final_deliverable": completed.final_output or payload,
    }


# Provider-neutral tool manifest
SUPRA_TOOLS = [
    decompose_objective,
    synthesize_strategy,
    verify_solution,
    restricted_python_executor,
    secure_sandbox_executor,
    record_checkpoint,
]

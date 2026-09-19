"""Tests del contrato de verificación honesta (auditoría hallazgo 1).

El defecto original: verify_solution asignaba invariants_preserved=True,
vulnerabilities=[] y verdict="PASS" con una confianza derivada de puntuaciones
prefijadas (feasibility*0.7+divergence*0.3+0.15) — sin ejecutar ninguna prueba.
Estas pruebas FALSAN ese comportamiento: ahora el verdict se deriva de la
evidencia ejecutada, y NOT_EVALUATED cuando no hay prueba que ejecutar.
"""

from __future__ import annotations

import tempfile

from supra_agentic.state import state_manager
from supra_agentic.tools import (
    decompose_objective,
    synthesize_strategy,
    verify_solution,
    _invariant_check,
    _run_invariant_evidence,
)
from supra_agentic.models import StrategyCandidate


def _project_with_candidate(tmpdir: str) -> str:
    state_manager.storage_dir = type(state_manager.storage_dir)(tmpdir)
    p = state_manager.create_project(objective="Pipeline de telemetría auto-recuperable")
    pid = p.project_id
    decompose_objective(pid, objective=p.objective, domain="data_pipeline")
    synthesize_strategy(pid, pathways_count=3, allow_disruptive=True)
    return pid


def test_verdict_deriva_de_evidencia_no_de_puntuaciones_prefijadas():
    """Dos candidatas con distintas feasibility NO fabrican la misma confianza:
    la confianza ahora es la fracción de invariantes con evidencia PASS."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pid = _project_with_candidate(tmpdir)
        report = verify_solution(pid)["report"]
        # la confianza es una fracción de invariantes con PASS, en [0,1]
        assert 0.0 <= report["confidence_score"] <= 1.0
        # y NO es el valor prefijado 0.79*0.7+0.88*0.3+0.15 del hallazgo
        assert abs(report["confidence_score"] - 0.967) > 1e-6


def test_not_evaluated_cuando_invariante_sin_prueba():
    """Un invariante sin prueba ejecutable queda NOT_EVALUATED, nunca PASS fabricado."""
    cand = StrategyCandidate(
        pathway_name="X",
        paradigm_type="CONSERVATIVE",
        hypothesis="algo",
        action_plan=["desplegar"],
    )
    evidence = _run_invariant_evidence(cand, ["Comportamiento cuántico emergente estable"])
    assert evidence[0]["status"] == "NOT_EVALUATED"


def test_invariante_no_cubierto_da_fail_con_contraejemplo():
    """Un candidato que NO cubre un invariante evaluable produce FAIL con refutación."""
    cand = StrategyCandidate(
        pathway_name="X",
        paradigm_type="DISRUPTIVE",
        hypothesis="sintetizar topología dinámica",
        action_plan=["romper topología estática", "sintetizar"],
    )
    evidence = _run_invariant_evidence(
        cand, ["Deterministic reproducibility of core verification evidence"]
    )
    assert evidence[0]["status"] == "FAIL"
    assert evidence[0]["counterexample"]  # refutación concreta registrada


def test_invariante_cubierto_da_pass():
    """Un candidato que SÍ cubre el invariante produce PASS."""
    cand = StrategyCandidate(
        pathway_name="X",
        paradigm_type="CONSERVATIVE",
        hypothesis="reproducibilidad determinista por semilla",
        action_plan=["fijar semilla", "verificar determinismo"],
    )
    evidence = _run_invariant_evidence(
        cand, ["Deterministic reproducibility of core verification evidence"]
    )
    assert evidence[0]["status"] == "PASS"


def test_invariant_check_sin_prueba_devuelve_none():
    """Un invariante sin mapeo ejecutable devuelve None (queda NOT_EVALUATED)."""
    assert _invariant_check("propiedad no mapeada a ninguna prueba") is None

"""Regression tests: the exported dossier must not execute or fabricate content.

Covers SUP-02 (stored XSS in the HTML dossier) and the presentation half of
SUP-04 (a missing verification must never be rendered as PASS).
"""

from __future__ import annotations

import html

from supra_agentic.dossier import export_full_html_dossier
from supra_agentic.models import (
    ProjectPosture,
    StrategyCandidate,
    StructuredDecomposition,
    TaskmasterStage,
    VerificationReport,
)

XSS = "<script>alert('xss')</script>"


def _posture(**overrides) -> ProjectPosture:
    base = dict(
        project_id="probe-xss",
        objective="Plain objective",
        stage=TaskmasterStage.COMPLETED,
        created_at=0.0,
        updated_at=0.0,
    )
    base.update(overrides)
    return ProjectPosture(**base)


def test_objective_script_is_escaped() -> None:
    dossier = export_full_html_dossier(_posture(objective=f"objective {XSS}"))

    assert XSS not in dossier
    assert html.escape(XSS, quote=True) in dossier


def test_invariants_and_candidate_are_escaped() -> None:
    decomposition = StructuredDecomposition(
        domain="cloud_security",
        core_objective="core",
        invariants=[f"<img src=x onerror=alert(1)> {XSS}"],
    )
    candidate = StrategyCandidate(
        pathway_name="</text><script>alert(2)</script>",
        paradigm_type="<b>ORTHOGONAL</b>",
        hypothesis=f"hypothesis {XSS}",
        is_selected=True,
    )
    dossier = export_full_html_dossier(
        _posture(decomposition=decomposition, selected_candidate=candidate)
    )

    assert "<img src=x onerror=alert(1)>" not in dossier
    assert "</text><script>" not in dossier
    assert "<b>ORTHOGONAL</b>" not in dossier
    assert XSS not in dossier
    assert "&lt;img src=x onerror=alert(1)&gt;" in dossier
    assert "&lt;script&gt;" in dossier


def test_missing_verification_is_not_rendered_as_pass() -> None:
    dossier = export_full_html_dossier(_posture())

    assert "NOT_EVALUATED" in dossier
    assert ">PASS<" not in dossier
    assert "H0 not declared" in dossier
    assert "H0 verified" not in dossier


def test_real_verdict_is_shown_unchanged() -> None:
    report = VerificationReport(
        candidate_id="cand-1",
        invariants_preserved=False,
        verdict="FAIL",
        confidence_score=0.0,
        rationale="evidence failed",
    )
    dossier = export_full_html_dossier(_posture(verification=report))

    assert "AST Fuzz (FAIL)" in dossier
    assert "NOT_EVALUATED" not in dossier


def test_plain_dossier_still_renders_its_content() -> None:
    dossier = export_full_html_dossier(_posture(objective="Diseñar un mesh sin secretos"))

    assert "SUPRA Autonomous Taskmaster Dossier" in dossier
    assert "Diseñar un mesh sin secretos" in dossier
    assert "probe-xss" in dossier
    assert "<svg" in dossier

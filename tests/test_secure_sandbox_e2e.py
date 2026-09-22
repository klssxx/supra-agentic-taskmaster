"""Real Docker smoke for the secure completion gate.

Normal unit-test jobs skip this module. CI's dedicated sandbox-e2e job enables it.
"""

from __future__ import annotations

import os

import pytest

from supra_agentic.models import TaskmasterStage, VerificationReport
from supra_agentic.state import state_manager
from supra_agentic.tools import (
    decompose_objective,
    record_checkpoint,
    restricted_python_executor,
    secure_sandbox_executor,
    synthesize_strategy,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SUPRA_RUN_DOCKER_E2E") != "1",
    reason="real Docker E2E is enabled only by the dedicated CI job",
)


def test_real_docker_sandbox_can_satisfy_completion_gate(tmp_path) -> None:
    state_manager.storage_dir = type(state_manager.storage_dir)(tmp_path)
    p = state_manager.create_project("real Docker sandbox completion smoke")
    decompose_objective(p.project_id, p.objective, domain="ci")
    synthesize_strategy(p.project_id, pathways_count=1, allow_disruptive=False)

    current = state_manager.get_project(p.project_id)
    assert current is not None
    selected = current.selected_candidate
    assert selected is not None
    state_manager.record_verification(
        p.project_id,
        VerificationReport(
            candidate_id=selected.candidate_id,
            invariants_preserved=True,
            invariants_checked=["CI fixture: secure isolation gate"],
            vulnerabilities_detected=[],
            confidence_score=1.0,
            verdict="PASS",
            rationale="CI_FIXTURE_ONLY: isolates sandbox plumbing from verifier quality.",
            evidence=[{"status": "PASS", "scope": "CI_FIXTURE_ONLY"}],
        ),
    )

    restricted = restricted_python_executor(p.project_id)
    assert restricted["restricted_execution_result"]["passed"] is True
    assert restricted["restricted_execution_result"]["identity_bound"] is True

    sandbox = secure_sandbox_executor(p.project_id)
    assert sandbox["status"] == "success"
    assert sandbox["secure_sandbox_status"] == "ISOLATED_BOUND_PASS"
    receipt = sandbox["secure_sandbox_result"]
    assert receipt["passed"] is True
    assert receipt["identity_bound"] is True
    assert receipt["isolation_verified"] is True
    assert receipt["image_id"].startswith("sha256:")
    assert receipt["network_isolated"] is True
    assert receipt["read_only_root"] is True
    assert receipt["capabilities_dropped"] is True
    assert receipt["no_new_privileges"] is True
    assert receipt["non_root_user"] is True
    assert receipt["resource_limits_applied"] is True

    final = record_checkpoint(
        p.project_id,
        deliverable_title="Docker sandbox CI smoke",
        summary="CI-only workflow completion after real isolated execution.",
    )
    assert final["stage"] == TaskmasterStage.COMPLETED.value
    assert final["final_deliverable"]["secure_sandbox_status"] == "ISOLATED_BOUND_PASS"
    assert final["final_deliverable"]["scientific_status"] == "NOT_VALIDATED"

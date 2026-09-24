"""Tests for SUPRA Project State Manager and Models."""

import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from supra_agentic.models import (
    RESTRICTED_EXECUTION_SEMANTICS_VERSION,
    SECURE_SANDBOX_SEMANTICS_VERSION,
    ProjectPosture,
    RestrictedExecutionResult,
    SecureSandboxResult,
    StrategyCandidate,
    StructuredDecomposition,
    Subtask,
    TaskmasterStage,
    VerificationReport,
    candidate_execution_identity,
    final_output_hash_matches,
)
from supra_agentic.state import (
    CompletionGateError,
    ProjectStateManager,
    ProjectTerminalStateError,
)


def _secure_result(
    identity: dict[str, str],
    *,
    passed: bool = True,
    isolated: bool = True,
) -> SecureSandboxResult:
    return SecureSandboxResult(
        execution_semantics_version=SECURE_SANDBOX_SEMANTICS_VERSION,
        candidate_id=identity["candidate_id"],
        mechanism_version=identity["mechanism_version"],
        claim_id=identity["claim_id"],
        protocol_version="sha256:" + "2" * 64,
        image="python:test",
        image_id="sha256:" + "3" * 64,
        passed=passed,
        observed_result="PASS" if passed else "FAIL",
        exit_code=0 if passed else 1,
        output_log="sandbox pass" if passed else "sandbox fail",
        duration_ms=2.0,
        network_isolated=isolated,
        read_only_root=isolated,
        capabilities_dropped=isolated,
        no_new_privileges=isolated,
        non_root_user=isolated,
        resource_limits_applied=isolated,
    )


def _verification_report(
    candidate: StrategyCandidate,
    **kwargs,
) -> VerificationReport:
    identity = candidate_execution_identity(candidate)
    return VerificationReport(
        candidate_id=candidate.candidate_id,
        mechanism_version=identity["mechanism_version"],
        claim_id=identity["claim_id"],
        **kwargs,
    )


def test_failed_project_cannot_be_reopened_by_state_mutators() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        project = sm.create_project(objective="failed projects are terminal")
        failed = sm.fail_project(project.project_id, "fatal workflow error")
        checkpoint_count = len(failed.checkpoints)

        decomposition = StructuredDecomposition(
            domain="general",
            core_objective="must not replay in place",
        )
        candidate = StrategyCandidate(
            pathway_name="Rejected replay",
            paradigm_type="ORTHOGONAL",
            hypothesis="A failed project must use a new project identity.",
            action_plan=["create a new project"],
        )

        with pytest.raises(ProjectTerminalStateError):
            sm.update_decomposition(project.project_id, decomposition)
        with pytest.raises(ProjectTerminalStateError):
            sm.add_candidates(project.project_id, [candidate])

        unchanged = sm.get_project(project.project_id)
        assert unchanged is not None
        assert unchanged.stage is TaskmasterStage.FAILED
        assert unchanged.decomposition is None
        assert unchanged.candidates == []
        assert len(unchanged.checkpoints) == checkpoint_count


def test_persistence_failure_rolls_back_in_memory_mutation(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        project = sm.create_project(objective="persistence rollback contract")
        candidate = StrategyCandidate(
            pathway_name="Transactional state",
            paradigm_type="ORTHOGONAL",
            hypothesis="Memory and disk remain aligned after write failure.",
            action_plan=["rollback the in-memory mutation"],
        )

        def fail_persistence(project_id: str) -> None:
            raise RuntimeError(f"simulated persistence failure for {project_id}")

        monkeypatch.setattr(sm, "_persist_project", fail_persistence)
        with pytest.raises(RuntimeError, match="simulated persistence failure"):
            sm.add_candidates(project.project_id, [candidate])

        in_memory = sm.get_project(project.project_id)
        assert in_memory is not None
        assert in_memory.stage is TaskmasterStage.RECEIVED
        assert in_memory.candidates == []
        assert in_memory.selected_candidate is None

        reloaded = ProjectStateManager(storage_dir=tmpdir).get_project(project.project_id)
        assert reloaded is not None
        assert reloaded.stage is TaskmasterStage.RECEIVED
        assert reloaded.candidates == []


def test_persisted_project_identity_must_match_filename() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        posture = ProjectPosture(
            project_id="real-project",
            objective="storage identity binding",
            stage=TaskmasterStage.RECEIVED,
            created_at=time.time(),
            updated_at=time.time(),
        )
        Path(tmpdir, "alias-project.json").write_text(
            posture.model_dump_json(),
            encoding="utf-8",
        )

        manager = ProjectStateManager(storage_dir=tmpdir)
        assert manager.get_project("alias-project") is None


def test_project_lifecycle_transitions():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        p = sm.create_project(objective="Design an autonomous zero-trust authentication protocol")

        assert p.stage == TaskmasterStage.RECEIVED
        assert p.objective == "Design an autonomous zero-trust authentication protocol"
        assert len(p.checkpoints) == 1

        # Stage 2: Decomposition
        decomp = StructuredDecomposition(
            domain="cybersecurity",
            core_objective="Zero-trust authentication without static secrets",
            invariants=["Memory safety", "Zero-leakage"],
            mutable_assumptions=["Centralized LDAP", "Bearer tokens"],
            risk_factors=["Replay attacks"],
            subtasks=[
                Subtask(
                    title="Formulate ephemeral challenge",
                    description="Challenge-response without stored secrets",
                    stage_target=TaskmasterStage.STRATIFIED,
                )
            ],
        )
        p2 = sm.update_decomposition(p.project_id, decomp)
        assert p2.stage == TaskmasterStage.STRUCTURED
        assert p2.decomposition is not None
        assert len(p2.checkpoints) == 2

        # Stage 3: Candidates
        cand1 = StrategyCandidate(
            pathway_name="Ephemeral Asymmetric Prover",
            paradigm_type="ORTHOGONAL",
            hypothesis="Zero-knowledge handshake eliminates bearer credential interception.",
            action_plan=["Generate ephemeral keypair", "Verify proof"],
            divergence_score=0.75,
            feasibility_score=0.88,
        )
        cand2 = StrategyCandidate(
            pathway_name="Rotating SMS OTP",
            paradigm_type="CONSERVATIVE",
            hypothesis="Standard OTP rotation.",
            action_plan=["Send SMS code"],
            divergence_score=0.10,
            feasibility_score=0.95,
        )
        p3 = sm.add_candidates(p.project_id, [cand1, cand2], select_best=True)
        assert p3.stage == TaskmasterStage.STRATIFIED
        assert p3.selected_candidate is not None
        assert p3.selected_candidate.pathway_name == "Ephemeral Asymmetric Prover"
        assert len(p3.checkpoints) == 3

        # Stage 4: Verification
        v_rep = _verification_report(
            cand1,
            invariants_preserved=True,
            invariants_checked=["Memory safety", "Zero-leakage"],
            vulnerabilities_detected=[],
            confidence_score=0.96,
            verdict="PASS",
            rationale="Proof verified without memory mutations.",
        )
        sm.record_verification(p.project_id, v_rep)

        # Stage 4b: trusted restricted execution
        expected_identity = candidate_execution_identity(cand1)
        execution_result = RestrictedExecutionResult(
            candidate_id=expected_identity["candidate_id"],
            mechanism_version=expected_identity["mechanism_version"],
            claim_id=expected_identity["claim_id"],
            protocol_version="sha256:test-protocol",
            execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
            action_type="RESTRICTED_CODE_RUN",
            passed=True,
            output_log="Restricted internal assertions passed.",
            duration_ms=4.2,
        )
        p4 = sm.record_restricted_execution(p.project_id, execution_result)
        assert p4.stage == TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED
        assert len(p4.restricted_execution_results) == 1

        # Stage 4c: externally isolated sandbox
        p4c = sm.record_secure_sandbox_execution(
            p.project_id,
            _secure_result(expected_identity),
        )
        assert p4c.stage == TaskmasterStage.SECURE_SANDBOX_VERIFIED
        assert len(p4c.secure_sandbox_results) == 1

        # Stage 5: Completion
        final_doc = {
            "deliverable": "Zero-Trust Ephemeral Prover Protocol v1",
            "audit_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        }
        p5 = sm.complete_project(p.project_id, final_doc)
        assert p5.stage == TaskmasterStage.COMPLETED
        assert p5.final_output is not None
        assert p5.final_output["deliverable"] == final_doc["deliverable"]
        assert p5.final_output["secure_sandbox_status"] == "IDENTITY_BOUND_ISOLATION_PASS"
        assert len(p5.checkpoints) == 7

        # Persistence check: load in fresh instance
        sm2 = ProjectStateManager(storage_dir=tmpdir)
        loaded = sm2.get_project(p.project_id)
        assert loaded is not None
        assert loaded.stage == TaskmasterStage.COMPLETED
        assert loaded.selected_candidate.pathway_name == "Ephemeral Asymmetric Prover"


def test_latest_restricted_revision_replaces_prior_pass():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        p = sm.create_project(objective="revision semantics")
        cand = StrategyCandidate(
            pathway_name="Path",
            paradigm_type="ORTHOGONAL",
            hypothesis="Current candidate hypothesis",
            action_plan=["step"],
            divergence_score=0.5,
            feasibility_score=0.5,
        )
        posture = sm.add_candidates(p.project_id, [cand], select_best=True)
        selected = posture.selected_candidate
        assert selected is not None
        identity = candidate_execution_identity(selected)

        passed = RestrictedExecutionResult(
            candidate_id=identity["candidate_id"],
            mechanism_version=identity["mechanism_version"],
            claim_id=identity["claim_id"],
            protocol_version="sha256:test-protocol",
            execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
            action_type="RESTRICTED_CODE_RUN",
            passed=True,
            output_log="pass",
            duration_ms=1.0,
        )
        assert sm.record_restricted_execution(p.project_id, passed).stage == (
            TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED
        )

        failed = RestrictedExecutionResult(
            candidate_id=identity["candidate_id"],
            mechanism_version=identity["mechanism_version"],
            claim_id=identity["claim_id"],
            protocol_version="sha256:test-protocol",
            execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
            action_type="RESTRICTED_CODE_RUN",
            passed=False,
            output_log="fail",
            duration_ms=1.0,
        )
        revised = sm.record_restricted_execution(p.project_id, failed)
        assert revised.stage == TaskmasterStage.STRATIFIED
        assert [item.passed for item in revised.restricted_execution_results] == [True, False]


def test_completed_workflow_is_revoked_immediately_by_latest_restricted_failure():
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        p = sm.create_project(objective="completed revision semantics")
        cand = StrategyCandidate(
            pathway_name="Path",
            paradigm_type="ORTHOGONAL",
            hypothesis="Current candidate hypothesis",
            action_plan=["step"],
            divergence_score=0.5,
            feasibility_score=0.5,
        )
        posture = sm.add_candidates(p.project_id, [cand], select_best=True)
        selected = posture.selected_candidate
        assert selected is not None
        identity = candidate_execution_identity(selected)

        def _result(passed: bool) -> RestrictedExecutionResult:
            return RestrictedExecutionResult(
                candidate_id=identity["candidate_id"],
                mechanism_version=identity["mechanism_version"],
                claim_id=identity["claim_id"],
                protocol_version="sha256:test-protocol",
                execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
                action_type="RESTRICTED_CODE_RUN",
                passed=passed,
                output_log="pass" if passed else "fail",
                duration_ms=1.0,
            )

        sm.record_verification(
            p.project_id,
            _verification_report(
                selected,
                invariants_preserved=True,
                invariants_checked=["bounded"],
                vulnerabilities_detected=[],
                confidence_score=1.0,
                verdict="PASS",
                rationale="Bounded test evidence.",
            ),
        )
        sm.record_restricted_execution(p.project_id, _result(True))
        sm.record_secure_sandbox_execution(p.project_id, _secure_result(identity))
        completed = sm.complete_project(
            p.project_id,
            {"workflow_status": "COMPLETED"},
        )
        assert completed.stage == TaskmasterStage.COMPLETED

        revised = sm.record_restricted_execution(p.project_id, _result(False))
        assert revised.stage == TaskmasterStage.STRATIFIED
        assert revised.final_output is not None
        assert revised.final_output["workflow_status"] == "BLOCKED"
        assert revised.final_output["completion_status"] == "BLOCKED"
        assert revised.final_output["restricted_execution_status"] == "BOUND_FAIL"
        assert revised.final_output["derived_completion_state_revalidated"] is True
        assert final_output_hash_matches(revised.final_output)


@pytest.mark.parametrize("verdict", ["FAIL", "NOT_EVALUATED"])
def test_completed_workflow_is_revoked_by_latest_verification_failure(verdict: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        project = sm.create_project(objective="latest verification controls completion")
        candidate = StrategyCandidate(
            pathway_name="Current evidence path",
            paradigm_type="ORTHOGONAL",
            hypothesis="Current evidence must remain passing.",
            action_plan=["bind every gate to the selected candidate"],
        )
        posture = sm.add_candidates(project.project_id, [candidate], select_best=True)
        selected = posture.selected_candidate
        assert selected is not None
        identity = candidate_execution_identity(selected)
        sm.record_verification(
            project.project_id,
            _verification_report(selected, verdict="PASS", confidence_score=1.0),
        )
        sm.record_restricted_execution(
            project.project_id,
            RestrictedExecutionResult(
                candidate_id=identity["candidate_id"],
                mechanism_version=identity["mechanism_version"],
                claim_id=identity["claim_id"],
                protocol_version="sha256:verification-revision",
                execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
                action_type="RESTRICTED_CODE_RUN",
                passed=True,
                output_log="pass",
                duration_ms=1.0,
            ),
        )
        sm.record_secure_sandbox_execution(project.project_id, _secure_result(identity))
        completed = sm.complete_project(
            project.project_id,
            {"workflow_status": "COMPLETED", "completion_status": "COMPLETED"},
        )
        assert completed.final_output is not None
        original_hash = completed.final_output["audit_sha256"]
        assert final_output_hash_matches(completed.final_output)

        revised = sm.record_verification(
            project.project_id,
            _verification_report(selected, verdict=verdict, confidence_score=0.0),
        )

        assert revised.stage is TaskmasterStage.SECURE_SANDBOX_VERIFIED
        assert revised.final_output is not None
        assert revised.final_output["workflow_status"] == "BLOCKED"
        assert revised.final_output["completion_status"] == "BLOCKED"
        assert revised.final_output["verification_verdict"] == verdict
        assert revised.final_output["superseded_audit_sha256"] == original_hash
        assert revised.final_output["audit_sha256"] != original_hash
        assert final_output_hash_matches(revised.final_output)


def test_tampered_completed_payload_is_invalidated_and_downgraded_on_load() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        project = sm.create_project(objective="tampered payload must not remain completed")
        candidate = StrategyCandidate(
            pathway_name="Integrity path",
            paradigm_type="ORTHOGONAL",
            hypothesis="The final payload remains integrity-addressed.",
            action_plan=["verify the final payload hash on load"],
        )
        posture = sm.add_candidates(project.project_id, [candidate], select_best=True)
        selected = posture.selected_candidate
        assert selected is not None
        identity = candidate_execution_identity(selected)
        sm.record_verification(
            project.project_id,
            _verification_report(selected, verdict="PASS", confidence_score=1.0),
        )
        sm.record_restricted_execution(
            project.project_id,
            RestrictedExecutionResult(
                candidate_id=identity["candidate_id"],
                mechanism_version=identity["mechanism_version"],
                claim_id=identity["claim_id"],
                protocol_version="sha256:tamper-test",
                execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
                action_type="RESTRICTED_CODE_RUN",
                passed=True,
                output_log="pass",
                duration_ms=1.0,
            ),
        )
        sm.record_secure_sandbox_execution(project.project_id, _secure_result(identity))
        completed = sm.complete_project(
            project.project_id,
            {"workflow_status": "COMPLETED", "completion_status": "COMPLETED"},
        )
        assert completed.final_output is not None
        recorded_hash = completed.final_output["audit_sha256"]

        state_file = Path(tmpdir, f"{project.project_id}.json")
        persisted = completed.model_dump()
        persisted_output = persisted["final_output"]
        assert isinstance(persisted_output, dict)
        persisted_output["workflow_status"] = "TAMPERED"
        state_file.write_text(json.dumps(persisted), encoding="utf-8")

        reloaded = ProjectStateManager(storage_dir=tmpdir).get_project(project.project_id)
        assert reloaded is not None
        assert reloaded.stage is TaskmasterStage.SECURE_SANDBOX_VERIFIED
        assert reloaded.final_output is not None
        assert "audit_sha256" not in reloaded.final_output
        assert reloaded.final_output["rejected_audit_sha256"] == recorded_hash
        assert reloaded.final_output["integrity_status"] == "INVALIDATED_BY_REVALIDATION"
        assert reloaded.final_output["workflow_status"] == "BLOCKED"


@pytest.mark.parametrize("verdict", ["FAIL", "NOT_EVALUATED"])
def test_completion_gate_rejects_failed_or_missing_verification(verdict: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        p = sm.create_project(objective="completion gate verification semantics")
        cand = StrategyCandidate(
            pathway_name="Bound Path",
            paradigm_type="ORTHOGONAL",
            hypothesis="Bound hypothesis",
            action_plan=["bounded step"],
            divergence_score=0.5,
            feasibility_score=0.5,
        )
        posture = sm.add_candidates(p.project_id, [cand], select_best=True)
        selected = posture.selected_candidate
        assert selected is not None
        identity = candidate_execution_identity(selected)
        sm.record_verification(
            p.project_id,
            _verification_report(
                selected,
                invariants_preserved=False,
                invariants_checked=["bounded"],
                vulnerabilities_detected=["bounded"],
                confidence_score=0.0,
                verdict=verdict,
                rationale="No passing verification evidence.",
            ),
        )
        sm.record_restricted_execution(
            p.project_id,
            RestrictedExecutionResult(
                candidate_id=identity["candidate_id"],
                mechanism_version=identity["mechanism_version"],
                claim_id=identity["claim_id"],
                protocol_version="sha256:test-protocol",
                execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
                action_type="RESTRICTED_CODE_RUN",
                passed=True,
                output_log="restricted pass",
                duration_ms=1.0,
            ),
        )
        sm.record_secure_sandbox_execution(p.project_id, _secure_result(identity))

        with pytest.raises(CompletionGateError):
            sm.complete_project(p.project_id, {"workflow_status": "COMPLETED"})

        blocked = sm.get_project(p.project_id)
        assert blocked is not None
        assert blocked.stage != TaskmasterStage.COMPLETED
        assert blocked.final_output is None
        assert blocked.checkpoints[-1].title == "Completion Gate Blocked"


def test_completion_gate_requires_current_bound_execution_pass() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        p = sm.create_project(objective="completion execution gate semantics")
        cand = StrategyCandidate(
            pathway_name="Bound Path",
            paradigm_type="ORTHOGONAL",
            hypothesis="Bound hypothesis",
            action_plan=["bounded step"],
            divergence_score=0.5,
            feasibility_score=0.5,
        )
        posture = sm.add_candidates(p.project_id, [cand], select_best=True)
        selected = posture.selected_candidate
        assert selected is not None
        sm.record_verification(
            p.project_id,
            _verification_report(
                selected,
                invariants_preserved=True,
                invariants_checked=["bounded"],
                vulnerabilities_detected=[],
                confidence_score=1.0,
                verdict="PASS",
                rationale="Verification passes but execution is absent.",
            ),
        )

        with pytest.raises(CompletionGateError):
            sm.complete_project(p.project_id, {"workflow_status": "COMPLETED"})

        blocked = sm.get_project(p.project_id)
        assert blocked is not None
        assert blocked.stage == TaskmasterStage.STRATIFIED
        assert blocked.final_output is None


def test_completion_gate_requires_current_isolated_sandbox_pass() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        p = sm.create_project(objective="completion sandbox gate semantics")
        cand = StrategyCandidate(
            pathway_name="Bound Path",
            paradigm_type="ORTHOGONAL",
            hypothesis="Bound hypothesis",
            action_plan=["bounded step"],
            divergence_score=0.5,
            feasibility_score=0.5,
        )
        posture = sm.add_candidates(p.project_id, [cand], select_best=True)
        selected = posture.selected_candidate
        assert selected is not None
        identity = candidate_execution_identity(selected)
        sm.record_verification(
            p.project_id,
            _verification_report(
                selected,
                invariants_preserved=True,
                invariants_checked=["bounded"],
                vulnerabilities_detected=[],
                confidence_score=1.0,
                verdict="PASS",
                rationale="Verification passes.",
            ),
        )
        sm.record_restricted_execution(
            p.project_id,
            RestrictedExecutionResult(
                candidate_id=identity["candidate_id"],
                mechanism_version=identity["mechanism_version"],
                claim_id=identity["claim_id"],
                protocol_version="sha256:test-protocol",
                execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
                action_type="RESTRICTED_CODE_RUN",
                passed=True,
                output_log="restricted pass",
                duration_ms=1.0,
            ),
        )

        with pytest.raises(CompletionGateError, match="sandbox isolation smoke"):
            sm.complete_project(p.project_id, {"workflow_status": "COMPLETED"})

        blocked = sm.get_project(p.project_id)
        assert blocked is not None
        assert blocked.stage == TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED
        assert blocked.final_output is None

        secure = sm.record_secure_sandbox_execution(
            p.project_id,
            _secure_result(identity),
        )
        assert secure.stage == TaskmasterStage.SECURE_SANDBOX_VERIFIED
        completed = sm.complete_project(p.project_id, {"workflow_status": "COMPLETED"})
        assert completed.stage == TaskmasterStage.COMPLETED


def test_non_isolated_sandbox_receipt_cannot_satisfy_completion_gate() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        p = sm.create_project(objective="non-isolated receipt")
        cand = StrategyCandidate(
            pathway_name="Path",
            paradigm_type="ORTHOGONAL",
            hypothesis="Hypothesis",
            action_plan=["step"],
        )
        posture = sm.add_candidates(p.project_id, [cand], select_best=True)
        selected = posture.selected_candidate
        assert selected is not None
        identity = candidate_execution_identity(selected)
        sm.record_verification(
            p.project_id,
            _verification_report(
                selected,
                invariants_preserved=True,
                confidence_score=1.0,
                verdict="PASS",
            ),
        )
        sm.record_restricted_execution(
            p.project_id,
            RestrictedExecutionResult(
                candidate_id=identity["candidate_id"],
                mechanism_version=identity["mechanism_version"],
                claim_id=identity["claim_id"],
                protocol_version="sha256:test",
                execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
                action_type="RESTRICTED_CODE_RUN",
                passed=True,
                output_log="pass",
                duration_ms=1.0,
            ),
        )
        receipt = _secure_result(identity, isolated=False)
        assert receipt.isolation_verified is False
        sm.record_secure_sandbox_execution(p.project_id, receipt)
        with pytest.raises(CompletionGateError):
            sm.complete_project(p.project_id, {"workflow_status": "COMPLETED"})


def test_candidate_mechanism_revision_cannot_reuse_prior_completion_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        p = sm.create_project(objective="mechanism revision binding")
        original = StrategyCandidate(
            candidate_id="cand-stable",
            pathway_name="Path",
            paradigm_type="ORTHOGONAL",
            hypothesis="Original hypothesis",
            action_plan=["original step"],
            divergence_score=0.5,
            feasibility_score=0.5,
        )
        posture = sm.add_candidates(p.project_id, [original], select_best=True)
        selected = posture.selected_candidate
        assert selected is not None
        original_identity = candidate_execution_identity(selected)

        sm.record_verification(
            p.project_id,
            _verification_report(
                selected,
                invariants_preserved=True,
                invariants_checked=["bounded"],
                confidence_score=1.0,
                verdict="PASS",
            ),
        )
        sm.record_restricted_execution(
            p.project_id,
            RestrictedExecutionResult(
                candidate_id=original_identity["candidate_id"],
                mechanism_version=original_identity["mechanism_version"],
                claim_id=original_identity["claim_id"],
                protocol_version="sha256:test-protocol",
                execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
                action_type="RESTRICTED_CODE_RUN",
                passed=True,
                output_log="pass",
                duration_ms=1.0,
            ),
        )
        sm.record_secure_sandbox_execution(
            p.project_id,
            _secure_result(original_identity),
        )

        revised = StrategyCandidate(
            candidate_id=original.candidate_id,
            pathway_name=original.pathway_name,
            paradigm_type=original.paradigm_type,
            hypothesis="Revised hypothesis",
            action_plan=["revised step"],
            divergence_score=0.5,
            feasibility_score=0.5,
        )
        revised_posture = sm.add_candidates(
            p.project_id,
            [revised],
            select_best=True,
        )
        assert revised_posture.selected_candidate is not None
        revised_identity = candidate_execution_identity(revised_posture.selected_candidate)
        assert revised_identity["candidate_id"] == original_identity["candidate_id"]
        assert revised_identity["mechanism_version"] != original_identity["mechanism_version"]
        assert revised_posture.verification is None

        sm.record_verification(
            p.project_id,
            _verification_report(
                revised_posture.selected_candidate,
                invariants_preserved=True,
                invariants_checked=["bounded"],
                confidence_score=1.0,
                verdict="PASS",
            ),
        )
        with pytest.raises(CompletionGateError):
            sm.complete_project(p.project_id, {"workflow_status": "COMPLETED"})

        restricted = sm.record_restricted_execution(
            p.project_id,
            RestrictedExecutionResult(
                candidate_id=revised_identity["candidate_id"],
                mechanism_version=revised_identity["mechanism_version"],
                claim_id=revised_identity["claim_id"],
                protocol_version="sha256:test-protocol-2",
                execution_semantics_version=RESTRICTED_EXECUTION_SEMANTICS_VERSION,
                action_type="RESTRICTED_CODE_RUN",
                passed=True,
                output_log="pass revised",
                duration_ms=1.0,
            ),
        )
        assert restricted.stage == TaskmasterStage.RESTRICTED_EXECUTION_VERIFIED
        secure = sm.record_secure_sandbox_execution(
            p.project_id,
            _secure_result(revised_identity),
        )
        assert secure.stage == TaskmasterStage.SECURE_SANDBOX_VERIFIED
        completed = sm.complete_project(
            p.project_id,
            {"workflow_status": "COMPLETED"},
        )
        assert completed.stage == TaskmasterStage.COMPLETED

        legacy_payload = completed.model_dump()
        verification_payload = legacy_payload["verification"]
        assert isinstance(verification_payload, dict)
        verification_payload.pop("mechanism_version", None)
        verification_payload.pop("claim_id", None)
        reloaded = ProjectPosture.model_validate(legacy_payload)
        assert reloaded.stage == TaskmasterStage.SECURE_SANDBOX_VERIFIED
        assert reloaded.final_output is not None
        assert reloaded.final_output["workflow_status"] == "BLOCKED"
        assert reloaded.final_output["completion_status"] == "BLOCKED"


@pytest.mark.parametrize(
    "project_id",
    ["../escape", "..", "a/b", r"a\\b", ".hidden", "bad id", "x" * 65],
)
def test_project_id_rejects_path_traversal_and_unsafe_names(project_id: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        with pytest.raises(ValueError):
            sm.create_project(objective="safe storage identity", project_id=project_id)


def test_project_id_cannot_overwrite_existing_project() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        original = sm.create_project(objective="first project", project_id="safe-project")
        with pytest.raises(ValueError):
            sm.create_project(objective="replacement project", project_id="safe-project")
        loaded = sm.get_project(original.project_id)
        assert loaded is not None
        assert loaded.objective == "first project"


def test_concurrent_managers_cannot_overwrite_the_same_project_id(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        first = ProjectStateManager(storage_dir=tmpdir)
        second = ProjectStateManager(storage_dir=tmpdir)
        barrier = Barrier(2)
        first_persist = first._persist_project
        second_persist = second._persist_project

        def pause_first(project_id: str, *args, **kwargs) -> None:
            barrier.wait(timeout=5)
            first_persist(project_id, *args, **kwargs)

        def pause_second(project_id: str, *args, **kwargs) -> None:
            barrier.wait(timeout=5)
            second_persist(project_id, *args, **kwargs)

        monkeypatch.setattr(first, "_persist_project", pause_first)
        monkeypatch.setattr(second, "_persist_project", pause_second)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    first.create_project,
                    "first concurrent objective",
                    "shared-project",
                ),
                executor.submit(
                    second.create_project,
                    "second concurrent objective",
                    "shared-project",
                ),
            ]
            outcomes: list[ProjectPosture | Exception] = []
            for future in futures:
                try:
                    outcomes.append(future.result())
                except Exception as exc:
                    outcomes.append(exc)

        successes = [item for item in outcomes if isinstance(item, ProjectPosture)]
        failures = [item for item in outcomes if isinstance(item, Exception)]
        assert len(successes) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], ValueError)

        persisted = ProjectStateManager(storage_dir=tmpdir).get_project("shared-project")
        assert persisted is not None
        assert persisted.objective == successes[0].objective


def test_candidate_selection_is_unique_and_empty_sets_are_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        project = sm.create_project(objective="candidate selection invariant")
        candidates = [
            StrategyCandidate(
                pathway_name="Lower score",
                paradigm_type="CONSERVATIVE",
                hypothesis="Lower-scored candidate.",
                action_plan=["remain unselected"],
                feasibility_score=0.1,
                divergence_score=0.1,
                is_selected=True,
            ),
            StrategyCandidate(
                pathway_name="Higher score",
                paradigm_type="ORTHOGONAL",
                hypothesis="Higher-scored candidate.",
                action_plan=["be selected"],
                feasibility_score=0.9,
                divergence_score=0.9,
                is_selected=True,
            ),
        ]

        posture = sm.add_candidates(project.project_id, candidates, select_best=True)
        assert posture.selected_candidate is not None
        assert posture.selected_candidate.pathway_name == "Higher score"
        assert [candidate.is_selected for candidate in posture.candidates] == [False, True]

        checkpoint_count = len(posture.checkpoints)
        with pytest.raises(ValueError, match="at least one candidate"):
            sm.add_candidates(project.project_id, [], select_best=True)
        unchanged = sm.get_project(project.project_id)
        assert unchanged is not None
        assert len(unchanged.candidates) == 2
        assert len(unchanged.checkpoints) == checkpoint_count


@pytest.mark.parametrize("limit", [True, 0, -1, 101])
def test_list_projects_rejects_unbounded_or_invalid_limits(limit: object) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        sm = ProjectStateManager(storage_dir=tmpdir)
        with pytest.raises(ValueError, match="integer between 1 and 100"):
            sm.list_projects(limit=limit)  # type: ignore[arg-type]

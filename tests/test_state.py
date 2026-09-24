"""Tests for SUPRA Project State Manager and Models."""

import tempfile

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
)
from supra_agentic.state import CompletionGateError, ProjectStateManager


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

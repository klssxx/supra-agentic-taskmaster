"""Executable Anti-Goodhart sentinels for SUPRA observational STANDARD."""

from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import pytest
from supra_agentic.anti_goodhart.detectors import (
    DetectorSpec,
    execution_record_consistency,
)
from supra_agentic.anti_goodhart.gate import (
    GateEvidence,
    ObserverMode,
    StandardDisabledError,
    gate_evidence_satisfies,
    scope_fingerprint,
    standard_allowed,
)
from supra_agentic.anti_goodhart.observer import _observe_trace_after_gate, observe_trace
from supra_agentic.anti_goodhart.records import Diagnostic
from supra_agentic.anti_goodhart.store import (
    ObserverStore,
    ObserverStoreCorruptionError,
)
from supra_agentic.anti_goodhart.trace import (
    load_sealed_trace,
    project_public_posture,
    seal_public_posture,
    sealed_trace_record,
)

ROOT = Path(__file__).resolve().parents[2]


def _posture(*, latest_pass: bool = True, stage: str = "COMPLETED") -> dict[str, object]:
    status = "BOUND_PASS" if latest_pass else "BOUND_FAIL"
    return {
        "project_id": "proj-anti-goodhart",
        "objective": "SECRET_OBJECTIVE_SHOULD_NOT_EXPORT",
        "stage": stage,
        "selected_candidate": {
            "candidate_id": "cand-1",
            "paradigm_type": "ORTHOGONAL",
            "hypothesis": "SECRET_FREE_FORM_HYPOTHESIS",
            "action_plan": ["SECRET_ACTION"],
            "divergence_score": 0.7,
            "feasibility_score": 0.8,
        },
        "verification": {
            "verdict": "NOT_EVALUATED",
            "verification_scope": "TEXTUAL_STRATEGY_COVERAGE",
            "measurement_kind": "HEURISTIC_COVERAGE",
            "confidence_score": 0.0,
            "confidence_semantics": "FRACTION_OF_DECLARED_INVARIANTS_WITH_HEURISTIC_PASS",
            "rationale": "SECRET_RATIONALE",
            "evidence": [{"secret": "SECRET_EVIDENCE"}],
        },
        "restricted_execution_results": [
            {
                "execution_id": "exec-1",
                "execution_semantics_version": 2,
                "candidate_id": "cand-1",
                "mechanism_version": "sha256:mechanism",
                "claim_id": "claim-1",
                "protocol_version": "sha256:protocol",
                "observed_result": "PASS" if latest_pass else "FAIL",
                "action_type": "RESTRICTED_CODE_RUN",
                "passed": latest_pass,
                "output_log": "SECRET_OUTPUT_LOG",
                "error_type": None if latest_pass else "RuntimeError",
                "duration_ms": 1.0,
                "execution_classification": "RESTRICTED_EXECUTION",
                "result_scope": "RESTRICTED_EXECUTION_ONLY",
                "scientific_validation": False,
                "process_isolated": False,
                "secure_for_untrusted_code": False,
                "identity_bound": True,
            }
        ],
        "checkpoints": [
            {
                "checkpoint_id": "chk-1",
                "stage": "STRATIFIED",
                "title": "Strategy selected",
                "evidence_summary": "SECRET_CHECKPOINT_EVIDENCE",
                "actor": "system:test",
            }
        ],
        "final_output": {
            "workflow_status": "COMPLETED",
            "verification_status": "NOT_EVALUATED",
            "verification_scope": "TEXTUAL_STRATEGY_COVERAGE",
            "restricted_execution_status": status,
            "restricted_execution_identity_bound": True,
            "scientific_status": "NOT_VALIDATED",
            "h0_status": "NOT_EVALUATED",
            "hash_semantics": "INTEGRITY_NOT_TRUTH",
            "discriminant_protocol_status": "NOT_ESTABLISHED",
            "independent_confirmation_status": "NOT_ESTABLISHED",
            "learning_update_status": "NOT_APPLICABLE",
            "derived_execution_state_revalidated": True,
            "secret_extra": "SECRET_FINAL_OUTPUT",
        },
        "error_message": "SECRET_ERROR_MESSAGE",
    }


def _scope() -> str:
    return scope_fingerprint(
        runtime_version="test-runtime",
        export_schema="astra-supra-public-trace/1",
        detector_versions=[
            "traceability_integrity:1",
            "descriptive_distributions:1",
            "execution_record_consistency:1",
        ],
        isolation_profile="test-isolated-worker",
    )


def _full_gate() -> GateEvidence:
    return GateEvidence(
        scope_fingerprint=_scope(),
        g1_pass=True,
        g2_pass=True,
        g3_pass=True,
        g4_pass=True,
        all_applicable_rows_executed=True,
        sensitivity_controls_pass=True,
        deployment_scope_matches=True,
    )


def test_g1_public_posture_is_deterministic_immutable_and_excludes_free_form_inputs():
    posture = _posture()
    original = copy.deepcopy(posture)
    first = seal_public_posture(posture)
    second = seal_public_posture(posture)
    assert first == second

    serialized = first.payload_json
    for secret in (
        "SECRET_OBJECTIVE_SHOULD_NOT_EXPORT",
        "SECRET_FREE_FORM_HYPOTHESIS",
        "SECRET_ACTION",
        "SECRET_RATIONALE",
        "SECRET_EVIDENCE",
        "SECRET_OUTPUT_LOG",
        "SECRET_CHECKPOINT_EVIDENCE",
        "SECRET_FINAL_OUTPUT",
        "SECRET_ERROR_MESSAGE",
    ):
        assert secret not in serialized

    posture["stage"] = "FAILED"
    assert first.payload()["stage"] == "COMPLETED"
    assert posture != original


def test_g1_projection_requires_stable_project_identity():
    posture = _posture()
    posture["project_id"] = ""
    with pytest.raises(ValueError, match="stable project_id"):
        project_public_posture(posture)


def test_activation_rule_is_binary_scope_bound_and_defaults_disabled():
    scope = _scope()
    assert gate_evidence_satisfies(None, current_scope_fingerprint=scope) is False
    assert gate_evidence_satisfies(_full_gate(), current_scope_fingerprint=scope) is True
    assert gate_evidence_satisfies(_full_gate(), current_scope_fingerprint="changed") is False
    assert standard_allowed(_full_gate(), current_scope_fingerprint=scope) is False

    stale = GateEvidence(
        scope_fingerprint=scope,
        g1_pass=True,
        g2_pass=True,
        g3_pass=False,
        g4_pass=True,
        all_applicable_rows_executed=True,
        sensitivity_controls_pass=True,
        deployment_scope_matches=True,
    )
    assert gate_evidence_satisfies(stale, current_scope_fingerprint=scope) is False


def test_off_creates_no_observer_state(tmp_path: Path):
    trace = seal_public_posture(_posture())
    root = tmp_path / "observer"
    result = observe_trace(trace, store=ObserverStore(root), mode=ObserverMode.OFF)
    assert result.inserted_diagnostics == 0
    assert result.failures == ()
    assert not root.exists()


def test_standard_public_api_stays_disabled_even_with_complete_gate(tmp_path: Path) -> None:
    trace = seal_public_posture(_posture())
    with pytest.raises(StandardDisabledError, match="STANDARD_DISABLED"):
        observe_trace(
            trace,
            store=ObserverStore(tmp_path / "observer"),
            mode=ObserverMode.STANDARD,
            gate_evidence=_full_gate(),
            current_scope_fingerprint=_scope(),
        )


def test_duplicate_delivery_is_idempotent_and_trace_is_unchanged(tmp_path: Path):
    trace = seal_public_posture(_posture())
    before = trace.payload_json
    store = ObserverStore(tmp_path / "observer")
    first = _observe_trace_after_gate(
        trace,
        store=store,
    )
    second = _observe_trace_after_gate(
        trace,
        store=store,
    )
    assert first.inserted_diagnostics == 3
    assert second.inserted_diagnostics == 0
    assert second.duplicate_diagnostics == 3
    assert len(store.read_diagnostics()) == 3
    assert trace.payload_json == before


def test_detector_failure_is_confined_and_secret_message_not_persisted(tmp_path: Path):
    trace = seal_public_posture(_posture())

    def broken(_trace):
        raise RuntimeError("SENTINEL_SECRET_DO_NOT_PERSIST")

    store = ObserverStore(tmp_path / "observer")
    result = _observe_trace_after_gate(
        trace,
        store=store,
        detectors=(DetectorSpec("broken", "1", broken),),
    )
    assert result.failures == ("broken:RuntimeError",)
    persisted = (tmp_path / "observer" / "observer_failures.jsonl").read_text(encoding="utf-8")
    assert "RuntimeError" in persisted
    assert "SENTINEL_SECRET_DO_NOT_PERSIST" not in persisted


def test_diagnostic_volume_changes_only_observer_domain(tmp_path: Path):
    trace = seal_public_posture(_posture())
    before = trace.payload_json

    def many(current_trace):
        return [
            Diagnostic(
                detector_id="volume",
                detector_version="1",
                trace_sha256=current_trace.payload_sha256,
                kind=f"sample-{index}",
                status="OBSERVED",
                message="descriptive sample",
                details={"index": index},
            )
            for index in range(100)
        ]

    result = _observe_trace_after_gate(
        trace,
        store=ObserverStore(tmp_path / "observer"),
        detectors=(DetectorSpec("volume", "1", many),),
    )
    assert result.inserted_diagnostics == 100
    assert trace.payload_json == before


def test_observer_restart_restores_only_observer_records(tmp_path: Path):
    trace = seal_public_posture(_posture())
    root = tmp_path / "observer"
    _observe_trace_after_gate(
        trace,
        store=ObserverStore(root),
    )
    restarted = ObserverStore(root)
    assert len(restarted.read_diagnostics()) == 3


def test_execution_consistency_reports_latest_fail_without_correcting_posture():
    posture = _posture(latest_pass=False, stage="RESTRICTED_EXECUTION_VERIFIED")
    original = copy.deepcopy(posture)
    trace = seal_public_posture(posture)
    diagnostics = execution_record_consistency(trace)
    assert diagnostics[0].status == "CONFLICT"
    assert "verified_stage_without_latest_bound_pass" in diagnostics[0].details["conflicts"]
    assert posture == original


def test_product_runtime_has_no_observer_import_path():
    critical = [
        "src/supra_agentic/runner.py",
        "src/supra_agentic/state.py",
        "src/supra_agentic/tools.py",
        "src/supra_agentic/service.py",
        "src/supra_agentic/mcp_handler.py",
        "src/supra_agentic/dossier.py",
    ]
    for relative in critical:
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "anti_goodhart" not in source, f"observer entered decisional path: {relative}"

    detector_source = (ROOT / "src" / "supra_agentic" / "anti_goodhart" / "detectors.py").read_text(
        encoding="utf-8"
    )
    assert "import random" not in detector_source
    assert "from random" not in detector_source


def test_sensitivity_control_detects_intentional_decisional_contamination():
    baseline = _posture()
    contaminated = copy.deepcopy(baseline)
    contaminated["stage"] = "FAILED"
    assert project_public_posture(baseline) != project_public_posture(contaminated)


def test_observer_storage_failure_is_confined_to_o_domain(tmp_path: Path):
    trace = seal_public_posture(_posture())
    before = trace.payload_json

    class BrokenStore(ObserverStore):
        def append_diagnostic(self, diagnostic):
            raise OSError("SENTINEL_STORAGE_SECRET")

    result = _observe_trace_after_gate(
        trace,
        store=BrokenStore(tmp_path / "observer"),
    )
    assert result.inserted_diagnostics == 0
    assert result.failures == (
        "observer_store:OSError",
        "observer_store:OSError",
        "observer_store:OSError",
    )
    assert trace.payload_json == before


def test_sealed_trace_rejects_forged_source_identity() -> None:
    trace = seal_public_posture(_posture())
    record = sealed_trace_record(trace)
    record["source"] = "FORGED_SOURCE"
    with pytest.raises(ValueError, match="source"):
        load_sealed_trace(record)


def _store_diagnostic(message: str = "canonical diagnostic") -> Diagnostic:
    return Diagnostic(
        detector_id="store-sentinel",
        detector_version="1",
        trace_sha256="a" * 64,
        kind="integrity",
        status="OBSERVED",
        message=message,
        details={"value": 1},
    )


def test_corrupt_semantic_record_fails_closed_without_mutation(tmp_path: Path) -> None:
    diagnostic = _store_diagnostic()
    store = ObserverStore(tmp_path / "observer")
    store.root.mkdir(parents=True, exist_ok=True)
    tampered = diagnostic.to_record()
    tampered["message"] = "tampered but parseable"
    store.diagnostics_path.write_text(
        json.dumps(tampered, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    before = store.diagnostics_path.read_bytes()

    with pytest.raises(ObserverStoreCorruptionError, match="invalid diagnostic"):
        store.read_diagnostics()
    with pytest.raises(ObserverStoreCorruptionError, match="invalid diagnostic"):
        store.append_diagnostic(diagnostic)

    assert store.diagnostics_path.read_bytes() == before


def test_store_rejects_parseable_nonfinite_diagnostic_record(tmp_path: Path) -> None:
    store = ObserverStore(tmp_path / "observer")
    store.root.mkdir(parents=True, exist_ok=True)
    poisoned = {
        "diagnostic_id": "forged-id",
        "detector_id": "poison",
        "detector_version": "1",
        "trace_sha256": "a" * 64,
        "kind": "integrity",
        "status": "OBSERVED",
        "message": "parseable non-finite record",
        "details": {"value": math.nan},
    }
    store.diagnostics_path.write_text(json.dumps(poisoned) + "\n", encoding="utf-8")
    before = store.diagnostics_path.read_bytes()

    with pytest.raises(ObserverStoreCorruptionError, match="invalid diagnostic"):
        store.read_diagnostics()
    with pytest.raises(ObserverStoreCorruptionError, match="invalid diagnostic"):
        store.append_diagnostic(_store_diagnostic())

    assert store.diagnostics_path.read_bytes() == before


def test_store_rejects_truncated_tail_without_worsening_file(tmp_path: Path) -> None:
    store = ObserverStore(tmp_path / "observer")
    store.root.mkdir(parents=True, exist_ok=True)
    store.diagnostics_path.write_bytes(b'{"diagnostic_id":"truncated"')
    before = store.diagnostics_path.read_bytes()

    with pytest.raises(ObserverStoreCorruptionError, match="invalid JSON"):
        store.append_diagnostic(_store_diagnostic())

    assert store.diagnostics_path.read_bytes() == before


def test_store_repairs_valid_tail_separator_before_append(tmp_path: Path) -> None:
    store = ObserverStore(tmp_path / "observer")
    store.root.mkdir(parents=True, exist_ok=True)
    first = _store_diagnostic("first")
    second = _store_diagnostic("second")
    store.diagnostics_path.write_text(
        json.dumps(first.to_record(), sort_keys=True),
        encoding="utf-8",
    )

    assert store.append_diagnostic(second) is True
    raw = store.diagnostics_path.read_bytes()
    assert raw.endswith(b"\n")
    assert len(raw.splitlines()) == 2
    assert [item["diagnostic_id"] for item in store.read_diagnostics()] == [
        first.diagnostic_id,
        second.diagnostic_id,
    ]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_public_trace_rejects_nonfinite_numbers(value: float) -> None:
    posture = _posture()
    posture["selected_candidate"]["divergence_score"] = value
    with pytest.raises(ValueError):
        seal_public_posture(posture)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_diagnostic_identity_rejects_nonfinite_details(value: float) -> None:
    diagnostic = Diagnostic(
        detector_id="nonfinite-sentinel",
        detector_version="1",
        trace_sha256="a" * 64,
        kind="integrity",
        status="OBSERVED",
        message="finite-json-required",
        details={"value": value},
    )
    with pytest.raises(ValueError):
        _ = diagnostic.diagnostic_id


def test_observer_store_deduplicates_across_processes(tmp_path: Path) -> None:
    root = tmp_path / "observer-multiprocess"
    start = tmp_path / "start.signal"
    process_count = 8
    child = """
import sys
import time
from pathlib import Path
from supra_agentic.anti_goodhart.records import Diagnostic
from supra_agentic.anti_goodhart.store import ObserverStore

root = Path(sys.argv[1])
ready = Path(sys.argv[2])
start = Path(sys.argv[3])
diagnostic = Diagnostic(
    detector_id="multiprocess-sentinel",
    detector_version="1",
    trace_sha256="a" * 64,
    kind="integrity",
    status="OBSERVED",
    message="same semantic diagnostic",
    details={"value": 1},
)
ready.write_text("ready", encoding="utf-8")
while not start.exists():
    time.sleep(0.005)
print(int(ObserverStore(root).append_diagnostic(diagnostic)), flush=True)
"""
    processes = []
    ready_paths = []
    for index in range(process_count):
        ready = tmp_path / f"ready-{index}.signal"
        ready_paths.append(ready)
        processes.append(
            subprocess.Popen(
                [sys.executable, "-c", child, str(root), str(ready), str(start)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        )

    deadline = time.monotonic() + 15.0
    while not all(path.exists() for path in ready_paths):
        assert time.monotonic() < deadline, "observer workers did not reach race barrier"
        time.sleep(0.01)
    start.write_text("go", encoding="utf-8")

    inserted = 0
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        inserted += int(stdout.strip())

    store = ObserverStore(root)
    diagnostics = store.read_diagnostics()
    assert inserted == 1
    assert len(diagnostics) == 1
    assert diagnostics[0]["diagnostic_id"]

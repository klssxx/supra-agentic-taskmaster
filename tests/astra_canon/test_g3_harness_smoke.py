"""Smoke and adversarial tests for the local SUPRA G3 verification harness."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from supra_agentic.anti_goodhart.observer import _observe_trace_after_gate
from supra_agentic.anti_goodhart.store import ObserverStore
from supra_agentic.anti_goodhart.trace import seal_public_posture, sealed_trace_record

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts" / "anti_goodhart_g3_probe.py"
WORKER = ROOT / "scripts" / "anti_goodhart_g3_worker.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("supra_g3_probe_under_test", PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _semantic_posture() -> dict[str, object]:
    candidate_a = {
        "candidate_id": "cand-a",
        "pathway_name": "Path A",
        "paradigm_type": "ORTHOGONAL",
        "hypothesis": "Hypothesis A",
        "action_plan": ["Action A"],
        "divergence_score": 0.7,
        "feasibility_score": 0.8,
        "is_selected": True,
    }
    candidate_b = {
        "candidate_id": "cand-b",
        "pathway_name": "Path B",
        "paradigm_type": "LATERAL",
        "hypothesis": "Hypothesis B",
        "action_plan": ["Action B"],
        "divergence_score": 0.6,
        "feasibility_score": 0.75,
        "is_selected": False,
    }
    return {
        "project_id": "proj-semantic",
        "stage": "COMPLETED",
        "candidates": [candidate_a, candidate_b],
        "selected_candidate": candidate_a,
        "restricted_execution_results": [],
        "checkpoints": [],
        "final_output": {},
    }


def test_g3_probe_help_and_no_auto_activation_contract() -> None:
    proc = subprocess.run(
        [sys.executable, str(PROBE), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0

    source = PROBE.read_text(encoding="utf-8")
    assert '"NOT_VERIFIED"' in source
    assert '"automatic_activation_permitted": False' in source
    assert 'STANDARD_RELEASE_STATE = "ALLOWED"' not in source
    assert '"PASS"' not in source


def test_g3_worker_requires_verification_guard() -> None:
    env = dict(os.environ)
    env.pop("ASTRA_G3_VERIFICATION", None)
    proc = subprocess.run(
        [sys.executable, str(WORKER), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert proc.returncode != 0
    assert "ASTRA_G3_VERIFICATION=1 is required" in (proc.stdout + proc.stderr)


def test_g3_worker_executes_synthetic_trace_without_product_release(
    tmp_path: Path,
) -> None:
    trace = seal_public_posture({"project_id": "g3-smoke", "stage": "COMPLETED"})
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        json.dumps(sealed_trace_record(trace), sort_keys=True),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["ASTRA_G3_VERIFICATION"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            str(WORKER),
            "--trace",
            str(trace_path),
            "--observer-root",
            str(tmp_path / "observer"),
            "--perturbation",
            "normal",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["verification_only"] is True
    assert payload["standard_release_changed"] is False
    assert payload["perturbation"] == "normal"


def test_g3_worker_latency_is_inside_elapsed_measurement(tmp_path: Path) -> None:
    trace = seal_public_posture({"project_id": "g3-latency", "stage": "COMPLETED"})
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        json.dumps(sealed_trace_record(trace), sort_keys=True),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["ASTRA_G3_VERIFICATION"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            str(WORKER),
            "--trace",
            str(trace_path),
            "--observer-root",
            str(tmp_path / "observer-latency"),
            "--perturbation",
            "latency",
            "--latency-ms",
            "300",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["elapsed_ms"] >= 250.0


def test_g3_probe_subprocess_is_bounded_by_timeout(monkeypatch, tmp_path: Path) -> None:
    probe = _load_probe()

    def fake_run(*args, **kwargs):
        timeout = kwargs.get("timeout")
        assert timeout is not None and timeout > 0
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=timeout)

    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    result = probe._worker(
        trace_path=tmp_path / "trace.json",
        observer_root=tmp_path / "observer",
        perturbation="normal",
        latency_ms=0,
    )
    assert result["worker_error_type"] == "VERIFICATION_WORKER_TIMEOUT"


def test_g3_probe_rejects_noop_perturbation_execution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    probe = _load_probe()
    stable = _semantic_posture()

    monkeypatch.setattr(probe, "_run_d", lambda *_args: (stable, 1.0))

    def noop_worker(**kwargs):
        return {
            "worker_exit": 0,
            "perturbation": kwargs["perturbation"],
            "inserted_diagnostics": 0,
            "duplicate_diagnostics": 0,
            "failures": [],
            "elapsed_ms": 0.0,
            "verification_only": True,
            "standard_release_changed": False,
        }

    monkeypatch.setattr(probe, "_worker", noop_worker)
    output = tmp_path / "noop-report.json"
    monkeypatch.setattr(sys, "argv", [str(PROBE), "--output", str(output)])

    assert probe.main() == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["probe_complete"] is False
    assert any(row["perturbation_ok"] is False for row in report["rows"])


def test_g3_semantic_comparator_detects_candidate_content_and_order() -> None:
    probe = _load_probe()
    baseline = _semantic_posture()

    changed_content = copy.deepcopy(baseline)
    changed_content["candidates"][0]["hypothesis"] = "MUTATED HYPOTHESIS"
    changed_content["selected_candidate"]["hypothesis"] = "MUTATED HYPOTHESIS"

    reordered = copy.deepcopy(baseline)
    reordered["candidates"] = list(reversed(reordered["candidates"]))

    baseline_digest = probe._digest(probe._normalized_public(baseline))
    assert probe._digest(probe._normalized_public(changed_content)) != baseline_digest
    assert probe._digest(probe._normalized_public(reordered)) != baseline_digest


def test_g3_probe_executes_every_local_perturbation_end_to_end(tmp_path: Path) -> None:
    output = tmp_path / "g3-report.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(PROBE),
            "--iterations",
            "2",
            "--latency-ms",
            "20",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "NOT_VERIFIED"
    assert report["probe_complete"] is True
    assert len(report["rows"]) == 7
    assert all(row["perturbation_ok"] is True for row in report["rows"])
    restart = next(row for row in report["rows"] if row["perturbation"] == "restart")
    assert restart["worker"]["restart_process_distinct"] is True


def test_incomplete_worker_cannot_create_causal_interference_claim(
    monkeypatch,
    tmp_path: Path,
) -> None:
    probe = _load_probe()
    baseline = _semantic_posture()
    mutated = copy.deepcopy(baseline)
    mutated["stage"] = "UNRELATED_DRIFT"
    calls = {"n": 0}

    def fake_run_d(*_args):
        calls["n"] += 1
        value = mutated if calls["n"] == 4 else baseline
        return copy.deepcopy(value), 1.0

    def failed_worker(**kwargs):
        return {
            "worker_exit": 7,
            "worker_error_type": "VERIFICATION_WORKER_FAILED",
            "perturbation": kwargs["perturbation"],
        }

    monkeypatch.setattr(probe, "_run_d", fake_run_d)
    monkeypatch.setattr(probe, "_worker", failed_worker)
    output = tmp_path / "incomplete-causality.json"
    monkeypatch.setattr(sys, "argv", [str(PROBE), "--output", str(output)])

    assert probe.main() == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "NOT_VERIFIED"
    assert report["reason"] == "local_probe_incomplete"
    assert report["rows"][0]["semantic_equal"] is False
    assert report["rows"][0]["perturbation_ok"] is False


def test_g4_two_consecutive_decisions_ignore_persisted_observer_state(tmp_path: Path) -> None:
    probe = _load_probe()
    objective = "Design a bounded deterministic service"
    d_root = tmp_path / "decisional"
    observer_root = tmp_path / "observer"

    first, _ = probe._run_d(objective, d_root, "g4-decision-1")
    first_trace = seal_public_posture(first)
    observed = _observe_trace_after_gate(
        first_trace,
        store=ObserverStore(observer_root),
    )
    assert observed.inserted_diagnostics >= 1
    assert ObserverStore(observer_root).read_diagnostics()

    second, _ = probe._run_d(objective, d_root, "g4-decision-2")

    assert probe._normalized_public(first) == probe._normalized_public(second)
